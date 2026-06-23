# -*- coding: utf-8 -*-
"""Export API router.

S8 扩展：在原有 Excel/bundle（legacy ReviewMatch 链路）基础上新增
- ``POST /tasks/{id}/export/report`` 报告多格式导出（pdf/docx/html）.
- ``POST /tasks/{id}/export/data`` 数据多范围导出（raw/standard/findings × excel/csv）.
- ``GET  /tasks/{id}/exports`` 导出历史列表.
- ``GET  /tasks/{id}/export/preview`` 取样预览（不生成产物）.

owner-only 复用 ``_load_owned_task`` 模式（404 unknown / 403 not owner）.
不删减精神：导出只读原数据 + 复制产物，不删原记录；导出历史产物文件保留可重新下载.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.permissions import check_task_permission
from app.database import get_db
from app.models import ExportFile, Task, User
from app.schemas.review import (
    DataExportRequest,
    ExportListItem,
    ExportPreviewResponse,
    ExportResponse,
    ExportRunRequest,
    ReportExportRequest,
)
from app.services.export_service import ExportService, load_export
from app.websocket.notifications import notify_user

router = APIRouter(tags=["exports"])


async def _load_owned_task(db: AsyncSession, task_id: int, current_user: User) -> Task:
    """复用 reports.py::_load_owned_task 模式：404 unknown / 403 not owner."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Task does not belong to current user")
    return task


@router.post("/tasks/{task_id}/export/excel", response_model=ExportResponse)
async def export_task_excel(
    task_id: int,
    request: ExportRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export task review results as Excel (legacy ReviewMatch 链路)."""
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
    """Export task review results as a skills bundle ZIP (legacy)."""
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


# ---------------------------------------------------------------------------
# S8 报告导出（pdf/docx/html）+ 数据导出（excel/csv）+ 历史 + 预览
# ---------------------------------------------------------------------------


@router.post("/tasks/{task_id}/export/report", response_model=ExportResponse)
async def export_task_report(
    task_id: int,
    request: ReportExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出该 task 当前章节化报告为 pdf/docx/html.

    数据源：S7 ReportChapter + 可选 ReportAnnotation. 报告不存在→404.
    落 ExportFile(scope="report", format=<fmt>). 返回 ExportResponse.
    """
    await _load_owned_task(db, task_id, current_user)
    try:
        export = await ExportService().export_report(
            db,
            task_id=task_id,
            fmt=request.format,
            include_annotations=request.include_annotations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await _notify_export_completed(current_user.id, export)
    return _export_response(export)


@router.post("/tasks/{task_id}/export/data", response_model=ExportResponse)
async def export_task_data(
    task_id: int,
    request: DataExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出 flow_records（raw/standard）或 findings 为 excel/csv.

    落 ExportFile(scope=<scope>, format=<fmt>). 返回 ExportResponse.
    """
    await _load_owned_task(db, task_id, current_user)
    try:
        export = await ExportService().export_data(
            db,
            task_id=task_id,
            scope=request.scope,
            fmt=request.format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await _notify_export_completed(current_user.id, export)
    return _export_response(export)


@router.get("/tasks/{task_id}/exports", response_model=list[ExportListItem])
async def list_task_exports(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出历史列表（ExportFile 按 created_at 降序）."""
    await _load_owned_task(db, task_id, current_user)
    exports = await ExportService().list_task_exports(db, task_id)
    return [
        ExportListItem(
            id=e.id,
            task_id=e.task_id,
            review_id=e.review_id,
            format=e.format,
            scope=e.scope,
            file_path=e.file_path,
            created_at=e.created_at,
        )
        for e in exports
    ]


@router.get("/tasks/{task_id}/export/preview", response_model=ExportPreviewResponse)
async def preview_task_export(
    task_id: int,
    scope: str = Query(..., description="report | raw | standard | findings"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取样预览（不生成产物）.

    report→前 2 章 content 文本 + 批注数；data→前 20 行 JSON.
    """
    await _load_owned_task(db, task_id, current_user)
    try:
        preview = await ExportService().preview_export(db, task_id, scope)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ExportPreviewResponse(
        scope=preview["scope"],
        sample=preview["sample"],
        annotation_count=preview.get("annotation_count"),
    )


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
    media_type = _media_type_for(export.format)
    return FileResponse(path, filename=path.name, media_type=media_type)


def _media_type_for(fmt: str) -> str:
    """Map export format → download media type (覆盖 S8 新增格式)."""
    return {
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html; charset=utf-8",
        "bundle": "application/zip",
    }.get(fmt, "application/octet-stream")


def _export_response(export) -> ExportResponse:
    return ExportResponse(
        id=export.id,
        task_id=export.task_id,
        review_id=export.review_id,
        format=export.format,
        file_path=export.file_path,
        scope=getattr(export, "scope", None),
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
            "scope": getattr(export, "scope", None),
        },
    )
