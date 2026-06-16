# -*- coding: utf-8 -*-
"""Export API router."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.permissions import check_task_permission
from app.database import get_db
from app.models import User
from app.schemas.review import ExportResponse, ExportRunRequest
from app.services.export_service import ExportService, load_export
from app.websocket.notifications import notify_user

router = APIRouter(tags=["exports"])


@router.post("/tasks/{task_id}/export/excel", response_model=ExportResponse)
async def export_task_excel(
    task_id: int,
    request: ExportRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export task review results as Excel."""
    if not await check_task_permission(db, current_user, task_id, required_role="write"):
        raise HTTPException(status_code=403, detail="Task access denied")

    try:
        export = await ExportService().export_excel(
            db,
            task_id=task_id,
            review_id=request.review_id if request else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await _notify_export_completed(current_user.id, export)
    return _export_response(export)


@router.post("/tasks/{task_id}/export/bundle", response_model=ExportResponse)
async def export_task_bundle(
    task_id: int,
    request: ExportRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export task review results as a skills bundle ZIP."""
    if not await check_task_permission(db, current_user, task_id, required_role="write"):
        raise HTTPException(status_code=403, detail="Task access denied")

    try:
        export = await ExportService().export_bundle(
            db,
            task_id=task_id,
            review_id=request.review_id if request else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await _notify_export_completed(current_user.id, export)
    return _export_response(export)


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download generated export artifact."""
    export = await load_export(db, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if not await check_task_permission(db, current_user, export.task_id):
        raise HTTPException(status_code=403, detail="Task access denied")

    path = Path(export.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if export.format == "excel"
        else "application/zip"
    )
    return FileResponse(path, filename=path.name, media_type=media_type)


def _export_response(export) -> ExportResponse:
    return ExportResponse(
        id=export.id,
        task_id=export.task_id,
        review_id=export.review_id,
        format=export.format,
        file_path=export.file_path,
        created_at=export.created_at,
    )


async def _notify_export_completed(user_id: int, export) -> None:
    await notify_user(
        user_id,
        event="export.completed",
        title="导出完成",
        message=f"任务 {export.task_id} {export.format} 导出已生成。",
        resource={
            "task_id": export.task_id,
            "review_id": export.review_id,
            "export_id": export.id,
            "format": export.format,
        },
    )
