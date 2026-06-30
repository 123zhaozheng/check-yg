# -*- coding: utf-8 -*-
"""Dashboard aggregation router.

``GET /api/dashboard`` returns a single payload summarizing the landing page:
KPI counts, in-progress task list, recent reports, and pending actions.

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
from ..models import Report, Review, Task, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# In-progress = not yet finalized. Drafts count as "active" work the user still
# needs to push forward, per docs §B1 "进行中任务数". analyzing = 标准化完成进入
# 分析/报告阶段，仍属"进行中"，只有报告定稿才会切到 completed。
_IN_PROGRESS_STATUSES = ("draft", "running", "paused", "analyzing")
# How many in-progress rows to surface on the dashboard.
_IN_PROGRESS_LIMIT = 8
_RECENT_REPORTS_LIMIT = 5
_PENDING_ACTIONS_LIMIT = 6


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


class DashboardPendingAction(BaseModel):
    id: int
    type: str  # "review_pending" | "report_pending"
    title: str
    task_id: int


class DashboardData(BaseModel):
    kpis: DashboardKpis
    in_progress_tasks: list[DashboardInProgressTask]
    recent_reports: list[DashboardRecentReport]
    pending_actions: list[DashboardPendingAction]


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

    # --- Pending actions (待我处理) ---------------------------------------
    # Pending reviews first, then reports on tasks without a finalized review.
    pending_review_query = (
        select(Review, Task.title)
        .join(Task, Task.id == Review.task_id)
        .where(Review.status == "pending", Task.archived.is_(False))
    )
    if not is_admin:
        pending_review_query = pending_review_query.where(Task.owner_id == current_user.id)
    pending_review_query = pending_review_query.order_by(Review.created_at.desc()).limit(
        _PENDING_ACTIONS_LIMIT
    )
    pending_actions: list[DashboardPendingAction] = []
    for review, title in (await db.execute(pending_review_query)).all():
        pending_actions.append(
            DashboardPendingAction(
                id=review.id,
                type="review_pending",
                title=f"待确认告警 · {title}",
                task_id=review.task_id,
            )
        )

    # Top up with recent reports (awaiting review/sign-off) if under the limit.
    if len(pending_actions) < _PENDING_ACTIONS_LIMIT:
        remaining = _PENDING_ACTIONS_LIMIT - len(pending_actions)
        report_actions_query = (
            select(Report, Task.title)
            .join(Task, Task.id == Report.task_id)
            .where(Task.archived.is_(False))
        )
        if not is_admin:
            report_actions_query = report_actions_query.where(Task.owner_id == current_user.id)
        report_actions_query = report_actions_query.order_by(Report.created_at.desc()).limit(
            remaining
        )
        for report, title in (await db.execute(report_actions_query)).all():
            pending_actions.append(
                DashboardPendingAction(
                    id=report.id,
                    type="report_pending",
                    title=f"待复核报告 · {title}",
                    task_id=report.task_id,
                )
            )

    return DashboardData(
        kpis=DashboardKpis(
            active_tasks=active_tasks,
            monthly_completed=monthly_completed,
            pending_alerts=pending_alerts,
            avg_audit_hours=avg_audit_hours,
        ),
        in_progress_tasks=in_progress_tasks,
        recent_reports=recent_reports,
        pending_actions=pending_actions,
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
