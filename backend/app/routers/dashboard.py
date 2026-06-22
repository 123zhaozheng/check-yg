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
# needs to push forward, per docs §B1 "进行中任务数".
_IN_PROGRESS_STATUSES = ("draft", "running", "paused")
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


def _stage_and_progress(task: Task) -> tuple[str, int]:
    """Derive a grayscale stage label + 0-100 progress from task state.

    Maps the 4-stage grayscale progression (docs §B1 / status-pill tones):
    导入=浅灰 → 清洗=中灰 → 分析=深灰 → 报告=黑底白字. We only have
    ``status`` + ``config.last_result`` to work with (live % comes via
    websocket, not stored on the row), so progress is a coarse heuristic.
    """
    status = task.status or "draft"
    config = task.config or {}
    has_last_result = bool(config.get("last_result"))

    if status == "failed":
        return "失败", 0
    if status == "cancelled":
        return "已取消", 0
    if status == "completed":
        return "已完成", 100
    if status == "running":
        # Without a persisted progress number we approximate by phase:
        # records present → past import, into cleaning/normalize.
        return ("清洗中", 60) if has_last_result else ("导入中", 20)
    if status == "paused":
        return ("已暂停", 50) if has_last_result else ("导入中", 20)
    # draft
    return "待开始", 0


@router.get("/", response_model=DashboardData)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate dashboard data for the current user."""
    is_admin = await check_admin_permission(db, current_user)

    # --- KPIs --------------------------------------------------------------
    active_query = _visibility_filter(
        select(func.count(Task.id)).where(Task.status.in_(_IN_PROGRESS_STATUSES)),
        current_user,
        is_admin,
    )
    active_tasks = (await db.execute(active_query)).scalar() or 0

    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    completed_query = _visibility_filter(
        select(func.count(Task.id)).where(
            Task.status == "completed",
            Task.completed_at.is_not(None),
            Task.completed_at >= month_start,
        ),
        current_user,
        is_admin,
    )
    monthly_completed = (await db.execute(completed_query)).scalar() or 0

    # Pending alerts = reviews still pending on tasks the user can see.
    # This is the cleanest "待处理告警" signal available without S3 fields.
    review_query = (
        select(func.count(Review.id))
        .join(Task, Task.id == Review.task_id)
        .where(Review.status == "pending")
    )
    review_query = _visibility_filter(review_query, current_user, is_admin)
    pending_alerts = (await db.execute(review_query)).scalar() or 0

    # Avg audit hours = mean(completed_at - created_at) in hours for completed
    # tasks. SQLite lacks `EXTRACT(EPOCH FROM ...)`; compute the avg in Python
    # from the fetched rows so the query is portable across pg + sqlite.
    avg_query = _visibility_filter(
        select(Task.created_at, Task.completed_at).where(
            Task.status == "completed",
            Task.completed_at.is_not(None),
        ),
        current_user,
        is_admin,
    )
    avg_rows = (await db.execute(avg_query)).all()
    avg_audit_hours = _mean_audit_hours(avg_rows)

    # --- In-progress task list --------------------------------------------
    in_progress_query = _visibility_filter(
        select(Task).where(Task.status.in_(_IN_PROGRESS_STATUSES)),
        current_user,
        is_admin,
    ).order_by(Task.updated_at.desc()).limit(_IN_PROGRESS_LIMIT)
    in_progress_tasks = [
        _in_progress_task(t) for t in (await db.execute(in_progress_query)).scalars().all()
    ]

    # --- Recent reports (join task for title, owner-scoped) ----------------
    recent_reports_query = (
        select(Report, Task.title)
        .join(Task, Task.id == Report.task_id)
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
        .where(Review.status == "pending")
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


def _in_progress_task(task: Task) -> DashboardInProgressTask:
    stage, progress = _stage_and_progress(task)
    return DashboardInProgressTask(
        id=task.id,
        title=task.title,
        employee_id=None,  # S3 lands the employee_id field; leave empty for now
        status=task.status,
        stage=stage,
        progress=progress,
        updated_at=task.updated_at,
    )


def _recent_report(report: Report, task_title: str) -> DashboardRecentReport:
    return DashboardRecentReport(
        id=report.id,
        task_id=report.task_id,
        task_title=task_title,
        created_at=report.created_at,
    )
