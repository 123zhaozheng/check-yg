# -*- coding: utf-8 -*-
"""Dashboard aggregation router.

``GET /api/dashboard`` returns a single payload summarizing the landing page:
KPI counts, in-progress task list, recent reports, and a per-task todo list
(四类待办：余额校验审批 / 关键词复核 / AI 分析确认 / 文档定稿).

Scope notes:
- Only aggregates existing Task/Report/Review fields — does NOT depend on any
  S3 additions (employee_id etc.). The "工号" column is left empty until S3
  lands the field; the frontend renders a placeholder.
- Visibility mirrors `customers.py`: admin sees all, others see only their own
  owned tasks (and reports/reviews under those tasks).
- KPI numbers are pure counts/averages — no hue. The frontend renders them with
  font weight + size, per the monochrome design (docs §B1).
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import Finding, KeywordHit, Report, Review, Task, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# In-progress = not yet finalized. Drafts count as "active" work the user still
# needs to push forward, per docs §B1 "进行中任务数". analyzing = 标准化完成进入
# 分析/报告阶段，仍属"进行中"，只有报告定稿才会切到 completed。
_IN_PROGRESS_STATUSES = ("draft", "running", "paused", "analyzing")
# How many in-progress rows to surface on the dashboard.
_IN_PROGRESS_LIMIT = 8
_RECENT_REPORTS_LIMIT = 5
# 「待我处理」按任务聚合的待办清单上限（对齐 _IN_PROGRESS_LIMIT）。
_TODOS_LIMIT = 8


class DashboardKpis(BaseModel):
    active_tasks: int
    monthly_completed: int
    pending_alerts: int
    avg_audit_hours: float


class DashboardInProgressTask(BaseModel):
    id: int
    title: str
    employee_id: Optional[str] = None  # placeholder until S3 lands the field
    status: str
    stage: str
    progress: int  # 0-100, grayscale bar on the frontend
    updated_at: datetime
    latest_report_status: Optional[str] = None  # 驱动 stage 细分（报告生成/已完成）


class DashboardRecentReport(BaseModel):
    id: int
    task_id: int
    task_title: str
    created_at: datetime


class DashboardTodoItem(BaseModel):
    type: str  # "balance_check" | "keyword" | "analysis" | "report_finalize"
    label: str  # "余额校验审批" | "关键词复核" | "AI 分析确认" | "文档定稿"
    action: str  # "审批" | "复核" | "确认" | "定稿" (按钮文案)
    count: Optional[int]  # 该类待办数；文档定稿为 None


class DashboardTodoTask(BaseModel):
    task_id: int
    title: str
    items: list[DashboardTodoItem]  # 按固定顺序，仅含有待办的类型
    latest_todo_at: datetime  # 排序键 = max(各 item 最近一条时间)


class DashboardData(BaseModel):
    kpis: DashboardKpis
    in_progress_tasks: list[DashboardInProgressTask]
    recent_reports: list[DashboardRecentReport]
    todos: list[DashboardTodoTask]


def _visibility_filter(query, current_user: User, is_admin: bool):
    """Owner-scoped unless admin (mirrors customers.py permission model)."""
    if not is_admin:
        query = query.where(Task.owner_id == current_user.id)
    return query


def _derive_stage_label(
    status: str,
    config: dict | None,
    latest_report_status: str | None,
) -> tuple[str, int]:
    """Derive the user-facing stage label + 0-100 progress from task state.

    单一真相源：dashboard 和 task list 都用这个，避免两端不一致。
    has_last_result / has_last_analysis 从 config 参数算，分支语义与原
    ``_stage_and_progress`` 一致。

    New status semantics: ``completed`` 严格表示"报告已定稿"（仅在
    finalize_report 设置），所以该分支直接给"已完成"/100。``analyzing`` 是
    标准化完成后的分析/报告阶段（属"进行中"），按 latest ``Report.status`` 与
    ``config.last_analysis_at`` 细分：清洗完成 → 分析中 → 报告生成（→ 已完成
    兜底，正常 finalize 会先把 task.status 改成 completed，不会走到 final 这支）。
    ``running`` 统一显示"清洗中"（避免首页与任务列表不一致），按是否有 result 分进度。
    """
    cfg = config or {}
    has_last_result = bool(cfg.get("last_result"))
    has_last_analysis = bool(cfg.get("last_analysis_at"))

    if status == "failed":
        return "失败", 0
    if status == "cancelled":
        return "已取消", 0
    if status == "completed":
        # completed = 报告已定稿（finalize_report 设置），即业务终态。
        return "已完成", 100
    if status == "analyzing":
        # 标准化完成进入分析/报告阶段，按报告/分析进度细分。
        if latest_report_status == "final":
            return "已完成", 100  # 兜底，正常不会走到（finalize 会先改 task.status）
        if latest_report_status in ("generating", "generated"):
            return "报告生成", 80
        if has_last_analysis:
            return "分析中", 60
        return "清洗完成", 40
    if status == "running":
        # 清洗中：统一文案，按是否已有 result 区分进度。
        return ("清洗中", 40) if has_last_result else ("清洗中", 20)
    if status == "paused":
        return ("已暂停", 30) if has_last_result else ("已暂停", 10)
    # draft
    return "待导入", 0


def _stage_and_progress(
    task: Task,
    latest_report_status: Optional[str] = None,
) -> tuple[str, int]:
    """Dashboard 薄包装：转调共享的 _derive_stage_label（单一真相源）。"""
    return _derive_stage_label(
        task.status or "draft", task.config, latest_report_status
    )


# Correlated subquery: latest Report.status per Task row, drives the stage
# subdivision above. SQLite + Postgres both accept correlated subqueries in
# the SELECT list; one round trip keeps the dashboard query cheap.
_LATEST_REPORT_STATUS = (
    select(Report.status)
    .where(Report.task_id == Task.id)
    .order_by(Report.created_at.desc())
    .limit(1)
    .scalar_subquery()
).label("latest_report_status")


@router.get("/", response_model=DashboardData)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate dashboard data for the current user."""
    is_admin = await check_admin_permission(db, current_user)

    # All dashboard queries hide archived rows by default — archived tasks
    # live in /tasks?archived=true, never on the landing page.
    def _hide_archived(q):
        return _visibility_filter(q, current_user, is_admin).where(
            Task.archived.is_(False)
        )

    # --- KPIs --------------------------------------------------------------
    active_query = _hide_archived(
        select(func.count(Task.id)).where(Task.status.in_(_IN_PROGRESS_STATUSES))
    )
    active_tasks = (await db.execute(active_query)).scalar() or 0

    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    completed_query = _hide_archived(
        select(func.count(Task.id)).where(
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= month_start,
        )
    )
    monthly_completed = (await db.execute(completed_query)).scalar() or 0

    # Pending alerts = reviews still pending on tasks the user can see.
    review_query = (
        select(func.count(Review.id))
        .join(Task, Task.id == Review.task_id)
        .where(Review.status == "pending", Task.archived.is_(False))
    )
    review_query = _visibility_filter(review_query, current_user, is_admin)
    pending_alerts = (await db.execute(review_query)).scalar() or 0

    # Avg audit hours = mean(completed_at - created_at) in hours for completed
    # tasks. SQLite lacks `EXTRACT(EPOCH FROM ...)`; compute the avg in Python
    # from the fetched rows so the query is portable across pg + sqlite.
    avg_query = _hide_archived(
        select(Task.created_at, Task.completed_at).where(
            Task.status == "completed",
            Task.completed_at.is_not(None),
        )
    )
    avg_rows = (await db.execute(avg_query)).all()
    avg_audit_hours = _mean_audit_hours(avg_rows)

    # --- In-progress task list --------------------------------------------
    in_progress_query = _hide_archived(
        select(Task, _LATEST_REPORT_STATUS)
        .where(Task.status.in_(_IN_PROGRESS_STATUSES))
        .order_by(Task.updated_at.desc())
        .limit(_IN_PROGRESS_LIMIT)
    )
    in_progress_rows = (await db.execute(in_progress_query)).all()
    in_progress_tasks = [
        _in_progress_task(task, latest_report_status)
        for task, latest_report_status in in_progress_rows
    ]

    # --- Recent reports (join task for title, owner-scoped) ----------------
    recent_reports_query = (
        select(Report, Task.title)
        .join(Task, Task.id == Report.task_id)
        .where(Task.archived.is_(False))
    )
    if not is_admin:
        recent_reports_query = recent_reports_query.where(Task.owner_id == current_user.id)
    recent_reports_query = recent_reports_query.order_by(Report.created_at.desc()).limit(
        _RECENT_REPORTS_LIMIT
    )
    recent_reports = [
        _recent_report(r, title)
        for r, title in (await db.execute(recent_reports_query)).all()
    ]

    # --- Todos (待我处理：按任务聚合的待办清单) ---------------------------
    # 重构自旧的扁平 pending_actions（review_pending 凑数 + report_pending 不过滤
    # status 的 bug）。现在按任务聚合四类真实待办：余额校验审批 / 关键词复核 /
    # AI 分析确认 / 文档定稿。任一任务有任意一类 pending → 产出一个
    # DashboardTodoTask；按 latest_todo_at 降序截 _TODOS_LIMIT。
    todos = await _build_todo_tasks(db, current_user, is_admin)

    return DashboardData(
        kpis=DashboardKpis(
            active_tasks=active_tasks,
            monthly_completed=monthly_completed,
            pending_alerts=pending_alerts,
            avg_audit_hours=avg_audit_hours,
        ),
        in_progress_tasks=in_progress_tasks,
        recent_reports=recent_reports,
        todos=todos,
    )


def _mean_audit_hours(rows: list[Any]) -> float:
    """Mean(completed_at - created_at) in hours across completed tasks.

    Skips rows with missing timestamps; returns 0.0 when none qualify.
    """
    hours: list[float] = []
    for row in rows:
        created_at, completed_at = row
        if not created_at or not completed_at:
            continue
        delta = completed_at - created_at
        hours.append(delta.total_seconds() / 3600.0)
    if not hours:
        return 0.0
    return round(sum(hours) / len(hours), 1)


def _in_progress_task(
    task: Task, latest_report_status: Optional[str] = None
) -> DashboardInProgressTask:
    stage, progress = _stage_and_progress(task, latest_report_status)
    return DashboardInProgressTask(
        id=task.id,
        title=task.title,
        employee_id=None,  # S3 lands the employee_id field; leave empty for now
        status=task.status,
        stage=stage,
        progress=progress,
        updated_at=task.updated_at,
        latest_report_status=latest_report_status,
    )


def _recent_report(report: Report, task_title: str) -> DashboardRecentReport:
    return DashboardRecentReport(
        id=report.id,
        task_id=report.task_id,
        task_title=task_title,
        created_at=report.created_at,
    )


# --- Todos (待我处理) 构造 ------------------------------------------------
# 四类待办的中文标签 + 按钮文案 + 固定顺序（balance_check → keyword →
# analysis → report_finalize）。route_suffix 由前端维护（跨层职责分离）。
_TODO_BALANCE_CHECK = ("balance_check", "余额校验审批", "审批")
_TODO_KEYWORD = ("keyword", "关键词复核", "复核")
_TODO_ANALYSIS = ("analysis", "AI 分析确认", "确认")
_TODO_REPORT_FINALIZE = ("report_finalize", "文档定稿", "定稿")


async def _build_todo_tasks(
    db: AsyncSession, current_user: User, is_admin: bool
) -> list[DashboardTodoTask]:
    """按任务聚合四类待办，返回按 latest_todo_at 降序、上限 _TODOS_LIMIT 的清单。

    四类（见 PRD §四类待办的数据边界）：
      - balance_check: Finding.source=='balance_check' AND status=='pending'
      - keyword:       KeywordHit.status=='pending'
      - analysis:      Finding.source IN (null,'rule') AND status=='pending'
      - report_finalize: Report.status=='generated'（存在即待办，count=None）

    任一任务有任意一类 → 产出 DashboardTodoTask；四类全空 → 不出现在结果。
    全部任务都没待办 → 返回 []（前端据此整块隐藏卡片）。
    """
    # 1) 候选任务集：当前用户可见 + 未归档。同时取 title/updated_at 供标题展示与
    #    latest_todo_at 兜底。这一批 task_id 是后续四类聚合查询的范围限定。
    tasks_query = _visibility_filter(
        select(Task.id, Task.title, Task.updated_at).where(Task.archived.is_(False)),
        current_user,
        is_admin,
    )
    task_rows = {row.id: row for row in (await db.execute(tasks_query)).all()}
    if not task_rows:
        return []

    visible_ids = list(task_rows.keys())

    # 2) 余额校验审批：Finding.source=='balance_check' AND status=='pending'。
    balance_rows = (
        await db.execute(
            select(
                Finding.task_id,
                func.count(Finding.id),
                func.max(Finding.updated_at),
            )
            .where(
                Finding.task_id.in_(visible_ids),
                Finding.source == "balance_check",
                Finding.status == "pending",
            )
            .group_by(Finding.task_id)
        )
    ).all()

    # 3) AI 分析确认：Finding.source IN (null,'rule') AND status=='pending'。
    #    source 可空，用 is_(None) 兼容历史/维度占位 finding。
    analysis_rows = (
        await db.execute(
            select(
                Finding.task_id,
                func.count(Finding.id),
                func.max(Finding.updated_at),
            )
            .where(
                Finding.task_id.in_(visible_ids),
                (Finding.source.is_(None)) | (Finding.source == "rule"),
                Finding.status == "pending",
            )
            .group_by(Finding.task_id)
        )
    ).all()

    # 4) 关键词复核：KeywordHit.status=='pending'。
    keyword_rows = (
        await db.execute(
            select(
                KeywordHit.task_id,
                func.count(KeywordHit.id),
                func.max(KeywordHit.updated_at),
            )
            .where(
                KeywordHit.task_id.in_(visible_ids),
                KeywordHit.status == "pending",
            )
            .group_by(KeywordHit.task_id)
        )
    ).all()

    # 5) 文档定稿：Report.status=='generated'（存在即待办）。取最新一条 generated
    #    报告的 created_at 作为该类时间戳。
    report_rows = (
        await db.execute(
            select(Report.task_id, func.max(Report.created_at))
            .where(
                Report.task_id.in_(visible_ids),
                Report.status == "generated",
            )
            .group_by(Report.task_id)
        )
    ).all()

    balance_by_task = {r[0]: (int(r[1]), r[2]) for r in balance_rows}
    analysis_by_task = {r[0]: (int(r[1]), r[2]) for r in analysis_rows}
    keyword_by_task = {r[0]: (int(r[1]), r[2]) for r in keyword_rows}
    report_by_task = {r[0]: r[1] for r in report_rows}

    # 6) 合并：只保留至少有一类待办的任务，按固定顺序拼 items，latest_todo_at
    #    取各类最近一条时间戳的 max；取不到回退 task.updated_at。
    todo_tasks: list[DashboardTodoTask] = []
    for task_id, row in task_rows.items():
        items: list[DashboardTodoItem] = []
        latest: list[datetime] = []

        if task_id in balance_by_task:
            count, ts = balance_by_task[task_id]
            items.append(
                DashboardTodoItem(
                    type=_TODO_BALANCE_CHECK[0],
                    label=_TODO_BALANCE_CHECK[1],
                    action=_TODO_BALANCE_CHECK[2],
                    count=count,
                )
            )
            if ts is not None:
                latest.append(ts)

        if task_id in keyword_by_task:
            count, ts = keyword_by_task[task_id]
            items.append(
                DashboardTodoItem(
                    type=_TODO_KEYWORD[0],
                    label=_TODO_KEYWORD[1],
                    action=_TODO_KEYWORD[2],
                    count=count,
                )
            )
            if ts is not None:
                latest.append(ts)

        if task_id in analysis_by_task:
            count, ts = analysis_by_task[task_id]
            items.append(
                DashboardTodoItem(
                    type=_TODO_ANALYSIS[0],
                    label=_TODO_ANALYSIS[1],
                    action=_TODO_ANALYSIS[2],
                    count=count,
                )
            )
            if ts is not None:
                latest.append(ts)

        if task_id in report_by_task:
            ts = report_by_task[task_id]
            items.append(
                DashboardTodoItem(
                    type=_TODO_REPORT_FINALIZE[0],
                    label=_TODO_REPORT_FINALIZE[1],
                    action=_TODO_REPORT_FINALIZE[2],
                    count=None,
                )
            )
            if ts is not None:
                latest.append(ts)

        if not items:
            continue

        latest_todo_at = max(latest) if latest else row.updated_at
        todo_tasks.append(
            DashboardTodoTask(
                task_id=task_id,
                title=row.title,
                items=items,
                latest_todo_at=latest_todo_at,
            )
        )

    todo_tasks.sort(key=lambda t: t.latest_todo_at, reverse=True)
    return todo_tasks[:_TODOS_LIMIT]
