# -*- coding: utf-8 -*-
"""Report API router."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.permissions import check_task_permission
from app.database import get_db
from app.models import User
from app.schemas.review import ReportResponse, ReportRunRequest
from app.services.report_service import ReportService, load_report

router = APIRouter(tags=["reports"])


@router.post("/tasks/{task_id}/report", response_model=ReportResponse)
async def generate_task_report(
    task_id: int,
    request: ReportRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a task report."""
    if not await check_task_permission(db, current_user, task_id, required_role="write"):
        raise HTTPException(status_code=403, detail="Task access denied")

    service = ReportService()
    try:
        report = await service.generate_report(
            db,
            task_id=task_id,
            review_id=request.review_id if request else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    content = await service.read_report_content(report)
    return _report_response(report, content)


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get report metadata and content."""
    report = await load_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not await check_task_permission(db, current_user, report.task_id):
        raise HTTPException(status_code=403, detail="Task access denied")

    content = await ReportService().read_report_content(report)
    return _report_response(report, content)


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download generated report file."""
    report = await load_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not await check_task_permission(db, current_user, report.task_id):
        raise HTTPException(status_code=403, detail="Task access denied")

    path = Path(report.content_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(path, filename=path.name, media_type="text/markdown; charset=utf-8")


def _report_response(report, content: str) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        task_id=report.task_id,
        review_id=report.review_id,
        format=report.format,
        content_path=report.content_path,
        content=content,
        created_at=report.created_at,
    )
