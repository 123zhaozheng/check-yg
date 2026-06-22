# -*- coding: utf-8 -*-
"""Task management router."""

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.dependencies import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Document, FlowRecordRow, Task, TaskLog, User
from ..services.extraction.runner import runner
from ..services.extraction.scanner import DocumentScanner

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Shared scanner so upload endpoints validate the same supported extensions
# as the extraction pipeline.
_SCANNER = DocumentScanner()


class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    document_folder: Optional[str] = None
    batch_size: int = 20
    confidence_threshold: int = 70
    # New-task dialog metadata (all optional — only `title` is required).
    employee_name: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    audit_start: Optional[datetime] = None
    audit_end: Optional[datetime] = None
    expected_channels: Optional[list[str]] = None


class TaskActionRequest(BaseModel):
    document_folder: Optional[str] = None
    batch_size: Optional[int] = None
    confidence_threshold: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    owner_id: int
    config: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    # Audited employee + review period + expected channels + archive flag.
    employee_name: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    audit_start: Optional[datetime] = None
    audit_end: Optional[datetime] = None
    expected_channels: Optional[list[str]] = None
    archived: bool = False

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    page: int
    page_size: int


def _task_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        owner_id=task.owner_id,
        config=task.config,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        employee_name=task.employee_name,
        employee_id=task.employee_id,
        department=task.department,
        audit_start=task.audit_start,
        audit_end=task.audit_end,
        expected_channels=task.expected_channels,
        archived=task.archived,
    )


def _next_upload_run_dir(task_id: int, config: dict) -> Path:
    """Compute a fresh per-run subfolder for uploaded files.

    Each create/append upload gets its own subfolder under
    ``UPLOAD_DIR/tasks/{task_id}/`` so same-named files in different runs do
    not overwrite each other and remain distinct documents (path-aware
    identity). The run counter is persisted in the task config.
    """
    run_index = int(config.get("upload_run_index") or 0) + 1
    config["upload_run_index"] = run_index
    folder = Path(settings.UPLOAD_DIR) / "tasks" / str(task_id) / f"run-{run_index}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _has_supported_file(files: List[UploadFile]) -> bool:
    """Return True if any uploaded file has a supported extension."""
    for upload in files:
        name = upload.filename or ""
        if is_supported_upload_name(name):
            return True
    return False


def is_supported_upload_name(filename: str) -> bool:
    name = Path(filename).name
    if not name or name.startswith("~$"):
        return False
    return Path(name).suffix.lower() in _SCANNER.supported_extensions


def _ensure_supported_files(files: List[UploadFile]) -> None:
    """Reject early if no supported file is present (before creating any task)."""
    if not _has_supported_file(files):
        raise HTTPException(
            status_code=422,
            detail="No supported files uploaded (expected .pdf/.docx/.xlsx/.xls)",
        )


async def _save_uploads(files: List[UploadFile], dest_dir: Path) -> tuple[Path, list[dict]]:
    """Persist uploaded files to dest_dir, keeping only supported extensions.

    Returns ``(dest_dir, saved_meta)`` where ``saved_meta`` is a list of
    ``{"filename", "original_path", "size_bytes"}`` for each saved file — used
    to pre-create Document rows with channel + size at upload time. Raises 422
    if no supported file was saved.
    """
    saved_meta: list[dict] = []
    for upload in files:
        filename = upload.filename or ""
        if not is_supported_upload_name(filename):
            continue
        safe_name = Path(filename).name
        if not safe_name:
            continue
        dest = dest_dir / safe_name
        size = 0
        with open(dest, "wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                size += len(chunk)
        saved_meta.append(
            {
                "filename": safe_name,
                "original_path": str(dest),
                "size_bytes": size,
            }
        )
    if not saved_meta:
        raise HTTPException(
            status_code=422,
            detail="No supported files uploaded (expected .pdf/.docx/.xlsx/.xls)",
        )
    return dest_dir, saved_meta


def _precreate_documents(
    db: AsyncSession, task_id: int, saved_meta: list[dict], channel: Optional[str]
) -> None:
    """Pre-create pending Document rows for uploaded files.

    Each row carries the channel label and file size so the documents list can
    show parsing status immediately (before extraction completes) and group by
    channel. The runner later updates these rows in place with flow_tables +
    completed/failed status; channel and size_bytes are preserved.
    """
    for meta in saved_meta:
        db.add(
            Document(
                task_id=task_id,
                filename=meta["filename"],
                original_path=meta["original_path"],
                status="pending",
                channel=channel,
                size_bytes=meta["size_bytes"],
            )
        )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    created_after: Optional[datetime] = Query(None),
    created_before: Optional[datetime] = Query(None),
    employee_id: Optional[str] = Query(None),
    archived: Optional[bool] = Query(None, description="true=归档, false=未归档, omitted=默认只看未归档"),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List tasks with pagination and filters.

    ``archived`` defaults to "未归档" (False) when omitted so the task list
    hides soft-deleted rows unless the caller explicitly asks for them.
    """
    query = select(Task)

    if status_filter:
        query = query.where(Task.status == status_filter)
    if stage:
        # Stage is the high-level pipeline step stored in Task.status; the list
        # filter passes it straight through (draft/import → running → completed).
        query = query.where(Task.status == stage)
    if created_after:
        query = query.where(Task.created_at >= created_after)
    if created_before:
        query = query.where(Task.created_at <= created_before)
    if employee_id:
        query = query.where(Task.employee_id == employee_id)
    if search:
        query = query.where(Task.title.ilike(f"%{search}%"))

    # Default: hide archived. Only when archived=True do we surface archived rows;
    # passing archived=False also hides them (explicit). Omitting archived keeps
    # the default-hide behavior, so archived tasks never leak into the main list.
    if archived is True:
        query = query.where(Task.archived.is_(True))
    else:
        query = query.where(Task.archived.is_(False))

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Task.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tasks = result.scalars().all()

    items = [_task_response(t) for t in tasks]

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an extraction task."""
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title cannot be empty")

    config = {
        "document_folder": request.document_folder,
        "batch_size": request.batch_size,
        "confidence_threshold": request.confidence_threshold,
    }
    task = Task(
        title=title,
        description=request.description,
        owner_id=current_user.id,
        status="draft",
        config=config,
        employee_name=request.employee_name,
        employee_id=request.employee_id,
        department=request.department,
        audit_start=request.audit_start,
        audit_end=request.audit_end,
        expected_channels=request.expected_channels,
    )
    db.add(task)
    await db.flush()
    db.add(TaskLog(task_id=task.id, level="info", message="Task created"))
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.post("/upload", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task_from_upload(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    batch_size: int = Form(20),
    confidence_threshold: int = Form(70),
    channel: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a task from uploaded files and start extraction immediately.

    Files are saved under a per-task upload subfolder, which becomes the
    extraction ``document_folder`` — no backend-local directory path is typed
    by the user. ``channel`` labels the uploaded files (e.g. 银行流水) and is
    persisted on each pre-created Document row.
    """
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Task title cannot be empty")
    _ensure_supported_files(files)

    config: dict[str, Any] = {
        "batch_size": batch_size,
        "confidence_threshold": confidence_threshold,
    }
    task = Task(
        title=clean_title,
        description=description,
        owner_id=current_user.id,
        status="draft",
        config=config,
    )
    db.add(task)
    await db.flush()
    db.add(TaskLog(task_id=task.id, level="info", message="Task created from upload"))
    await db.commit()
    await db.refresh(task)

    upload_dir = _next_upload_run_dir(task.id, config)
    _, saved_meta = await _save_uploads(files, upload_dir)
    _precreate_documents(db, task.id, saved_meta, channel)
    config["document_folder"] = str(upload_dir)
    task.config = config
    task.status = "running"
    task.completed_at = None
    db.add(TaskLog(task_id=task.id, level="info", message="Extraction started"))
    await db.commit()
    await db.refresh(task)

    try:
        await runner.start(
            task_id=task.id,
            owner_id=current_user.id,
            document_folder=str(upload_dir),
            batch_size=batch_size,
            confidence_threshold=confidence_threshold,
            append=False,
        )
    except ValueError as exc:
        task.status = "draft"
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _task_response(task)


@router.post("/{task_id}/append-upload", response_model=TaskResponse)
async def append_task_from_upload(
    task_id: int,
    batch_size: Optional[int] = Form(None),
    confidence_threshold: Optional[int] = Form(None),
    channel: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append uploaded documents to an existing task and start append extraction.

    Files land in a fresh per-run subfolder so same-named files from different
    append runs stay distinct (path-aware document identity). ``channel`` labels
    the appended files and is persisted on each pre-created Document row.
    """
    task = await _load_owned_task(db, task_id, current_user)
    if task.status == "running" or runner.is_running(task.id):
        raise HTTPException(status_code=409, detail="Task is already running")
    _ensure_supported_files(files)

    config = dict(task.config or {})
    upload_dir = _next_upload_run_dir(task.id, config)
    _, saved_meta = await _save_uploads(files, upload_dir)
    _precreate_documents(db, task.id, saved_meta, channel)

    bs = batch_size or int(config.get("batch_size") or 20)
    ct = confidence_threshold or int(config.get("confidence_threshold") or 70)
    append_folders = list(config.get("append_document_folders") or [])
    if str(upload_dir) not in append_folders:
        append_folders.append(str(upload_dir))
    config["append_document_folders"] = append_folders
    config["append_document_folder"] = str(upload_dir)
    config["document_folder"] = config.get("document_folder") or str(upload_dir)
    task.config = config
    task.status = "running"
    task.completed_at = None
    db.add(TaskLog(task_id=task.id, level="info", message="Append extraction started from upload"))
    await db.commit()
    await db.refresh(task)

    try:
        await runner.start(
            task_id=task.id,
            owner_id=current_user.id,
            document_folder=str(upload_dir),
            batch_size=bs,
            confidence_threshold=ct,
            append=True,
        )
    except ValueError as exc:
        task.status = "failed"
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _task_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get task details."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_response(task)


@router.post("/{task_id}/start", response_model=TaskResponse)
async def start_task(
    task_id: int,
    request: TaskActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start extraction for a task in the background."""
    task = await _load_owned_task(db, task_id, current_user)
    if task.status == "running" or runner.is_running(task.id):
        raise HTTPException(status_code=409, detail="Task is already running")

    config = dict(task.config or {})
    document_folder = request.document_folder or config.get("document_folder")
    if not document_folder:
        raise HTTPException(status_code=422, detail="document_folder is required")
    folder_path = Path(document_folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=422, detail="document_folder must be an existing directory")

    batch_size = request.batch_size or int(config.get("batch_size") or 20)
    confidence_threshold = request.confidence_threshold or int(config.get("confidence_threshold") or 70)
    config.update(
        {
            "document_folder": str(folder_path),
            "batch_size": batch_size,
            "confidence_threshold": confidence_threshold,
        }
    )
    task.config = config
    task.status = "running"
    task.completed_at = None
    db.add(TaskLog(task_id=task.id, level="info", message="Extraction started"))
    await db.commit()
    await db.refresh(task)

    try:
        await runner.start(
            task_id=task.id,
            owner_id=current_user.id,
            document_folder=str(folder_path),
            batch_size=batch_size,
            confidence_threshold=confidence_threshold,
            append=False,
        )
    except ValueError as exc:
        task.status = "draft"
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _task_response(task)


@router.post("/{task_id}/append", response_model=TaskResponse)
async def append_task_documents(
    task_id: int,
    request: TaskActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append new documents from another folder to an existing extraction task."""
    task = await _load_owned_task(db, task_id, current_user)
    if task.status == "running" or runner.is_running(task.id):
        raise HTTPException(status_code=409, detail="Task is already running")
    if not request.document_folder:
        raise HTTPException(status_code=422, detail="document_folder is required")
    folder_path = Path(request.document_folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=422, detail="document_folder must be an existing directory")

    config = dict(task.config or {})
    batch_size = request.batch_size or int(config.get("batch_size") or 20)
    confidence_threshold = request.confidence_threshold or int(config.get("confidence_threshold") or 70)
    # Track every appended folder, not just the latest, so the task keeps a
    # full history of source directories (mirrors the original document_folder list).
    append_folders = list(config.get("append_document_folders") or [])
    if str(folder_path) not in append_folders:
        append_folders.append(str(folder_path))
    config["append_document_folders"] = append_folders
    config["append_document_folder"] = str(folder_path)
    task.config = config
    task.status = "running"
    task.completed_at = None
    db.add(TaskLog(task_id=task.id, level="info", message="Append extraction started"))
    await db.commit()
    await db.refresh(task)

    try:
        await runner.start(
            task_id=task.id,
            owner_id=current_user.id,
            document_folder=str(folder_path),
            batch_size=batch_size,
            confidence_threshold=confidence_threshold,
            append=True,
        )
    except ValueError as exc:
        task.status = "failed"
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _task_response(task)


@router.post("/{task_id}/pause", response_model=TaskResponse)
async def pause_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause a running extraction task."""
    task = await _load_owned_task(db, task_id, current_user)
    paused = await runner.pause(task.id)
    if not paused:
        raise HTTPException(status_code=409, detail="Task is not running in this process")
    task.status = "paused"
    db.add(TaskLog(task_id=task.id, level="info", message="Extraction paused"))
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.post("/{task_id}/resume", response_model=TaskResponse)
async def resume_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume a paused extraction task."""
    task = await _load_owned_task(db, task_id, current_user)
    resumed = await runner.resume(task.id)
    if not resumed:
        raise HTTPException(status_code=409, detail="Task is not paused in this process")
    task.status = "running"
    db.add(TaskLog(task_id=task.id, level="info", message="Extraction resumed"))
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a running extraction task."""
    task = await _load_owned_task(db, task_id, current_user)
    cancelled = await runner.cancel(task.id)
    if not cancelled and task.status == "running":
        raise HTTPException(status_code=409, detail="Task is not running in this process")
    task.status = "cancelled"
    db.add(TaskLog(task_id=task.id, level="warning", message="Extraction cancelled"))
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.post("/{task_id}/archive", response_model=TaskResponse)
async def archive_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive a task (soft flag — data is never deleted)."""
    task = await _load_owned_task(db, task_id, current_user)
    task.archived = True
    db.add(TaskLog(task_id=task.id, level="info", message="Task archived"))
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.post("/{task_id}/unarchive", response_model=TaskResponse)
async def unarchive_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore an archived task back to the active list."""
    task = await _load_owned_task(db, task_id, current_user)
    task.archived = False
    db.add(TaskLog(task_id=task.id, level="info", message="Task unarchived"))
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a task by archiving it.

    Honors the 不删减 hard line — the row and all its audit data stay in the
    DB; we only flip ``archived`` so the task drops out of the default list.
    """
    task = await _load_owned_task(db, task_id, current_user)
    task.archived = True
    db.add(TaskLog(task_id=task.id, level="warning", message="Task soft-deleted (archived)"))
    await db.commit()
    return None


async def _load_owned_task(db: AsyncSession, task_id: int, current_user: User) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Task does not belong to current user")
    return task


# ---------------------------------------------------------------------------
# Document list / delete (S4 data import).
# Documents are pre-created at upload time (status="pending") and updated by
# the extraction runner. Soft-delete flips status to "deleted" — the row and
# raw files are never removed (不删减 hard line).
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    """One document row in the import page's file table."""

    id: int
    filename: str
    original_path: str
    channel: Optional[str] = None
    status: str
    size_bytes: Optional[int] = None
    created_at: datetime
    error_log: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int


def _document_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        original_path=doc.original_path,
        channel=doc.channel,
        status=doc.status,
        size_bytes=doc.size_bytes,
        created_at=doc.created_at,
        error_log=doc.error_log,
    )


@router.get("/{task_id}/documents", response_model=DocumentListResponse)
async def list_task_documents(
    task_id: int,
    channel: Optional[str] = Query(None),
    include_deleted: bool = Query(
        False, description="true=含软删行, omitted/false=默认隐藏 status=deleted"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List documents for a task, optionally filtered by channel.

    Soft-deleted rows (status="deleted") are hidden by default, mirroring the
    task list's default-hide behavior for archived rows. Pass
    ``include_deleted=true`` to surface them.
    """
    await _load_owned_task(db, task_id, current_user)

    query = select(Document).where(Document.task_id == task_id)
    if channel:
        query = query.where(Document.channel == channel)
    if not include_deleted:
        query = query.where(Document.status != "deleted")

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Document.created_at.desc())
    result = await db.execute(query)
    docs = result.scalars().all()

    return DocumentListResponse(
        items=[_document_response(d) for d in docs], total=total
    )


@router.delete(
    "/{task_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task_document(
    task_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a document (status -> "deleted"). Row and raw files stay.

    Honors the 不删减 hard line — never removes the DB row or the uploaded file.
    The document drops out of the default list (which hides status="deleted")
    but can be restored later or surfaced via include_deleted=true.
    """
    await _load_owned_task(db, task_id, current_user)

    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.task_id == task_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = "deleted"
    db.add(
        TaskLog(
            task_id=task_id,
            level="warning",
            message=f"Document soft-deleted: {doc.filename}",
        )
    )
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# S5 清洗标准化 — flow_records (record-of-truth), excluded view, restore,
# cleaning commit + export log. Owner-only, reuses _load_owned_task.
# 清洗不删减: every raw table row is persisted 1:1 (standard / unparsed /
# excluded) with raw_payload; restore marks rows restored but never deletes.
# ---------------------------------------------------------------------------


class RecordResponse(BaseModel):
    """One flow_records row — standard / unparsed / excluded."""

    id: int
    task_id: int
    document_id: Optional[int] = None
    channel: Optional[str] = None
    record_type: str
    row_index: int
    is_valid: bool
    transaction_time: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_account: Optional[str] = None
    amount: Optional[str] = None
    raw_amount: Optional[str] = None
    summary: Optional[str] = None
    transaction_type: Optional[str] = None
    raw_payload: Optional[dict[str, Any]] = None
    status: str
    exclude_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecordListResponse(BaseModel):
    items: List[RecordResponse]
    total: int
    page: int
    page_size: int


def _record_response(row: FlowRecordRow) -> RecordResponse:
    return RecordResponse(
        id=row.id,
        task_id=row.task_id,
        document_id=row.document_id,
        channel=row.channel,
        record_type=row.record_type,
        row_index=row.row_index,
        is_valid=bool(row.is_valid),
        transaction_time=row.transaction_time,
        counterparty_name=row.counterparty_name,
        counterparty_account=row.counterparty_account,
        amount=row.amount,
        raw_amount=row.raw_amount,
        summary=row.summary,
        transaction_type=row.transaction_type,
        raw_payload=row.raw_payload,
        status=row.status,
        exclude_reason=row.exclude_reason,
        created_at=row.created_at,
    )


@router.get("/{task_id}/records", response_model=RecordListResponse)
async def list_task_records(
    task_id: int,
    channel: Optional[str] = Query(None),
    record_type: Optional[str] = Query(
        None,
        description="standard | unparsed | excluded | all (default standard)",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List flow_records for a task, filtered by channel and record_type.

    Defaults to ``record_type=standard`` (the cleaned, downstream-usable rows).
    Pass ``record_type=all`` to surface every type, or ``unparsed``/``excluded``
    to inspect the 不删减保留的排除项.
    """
    await _load_owned_task(db, task_id, current_user)

    query = select(FlowRecordRow).where(FlowRecordRow.task_id == task_id)
    if channel:
        query = query.where(FlowRecordRow.channel == channel)
    if record_type == "all":
        pass  # no record_type filter — surface every type
    elif record_type:
        query = query.where(FlowRecordRow.record_type == record_type)
    else:
        query = query.where(FlowRecordRow.record_type == "standard")

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(FlowRecordRow.id.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.scalars().all()

    return RecordListResponse(
        items=[_record_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}/excluded", response_model=RecordListResponse)
async def list_task_excluded(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    record_type: Optional[str] = Query(
        None,
        description="excluded | unparsed (default both). Filters the 可捞回 view to one type so pagination composes per sub-tab.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List excluded + unparsed rows that are still active (not yet restored).

    These are the 不删减保留的可捞回项 — classifier-rejected table rows
    (excluded) and normalizer noise rows (unparsed). Restored rows drop out of
    this view but stay in the table.

    ``record_type`` optionally narrows to one type so the frontend's
    非流水表 / 噪音行 sub-tabs paginate independently (a mixed page filtered
    client-side would show empty slots when one type is sparse on a page).
    """
    await _load_owned_task(db, task_id, current_user)

    types = [record_type] if record_type in ("excluded", "unparsed") else ["excluded", "unparsed"]
    query = select(FlowRecordRow).where(
        FlowRecordRow.task_id == task_id,
        FlowRecordRow.record_type.in_(types),
        FlowRecordRow.status == "active",
    )
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(FlowRecordRow.id.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.scalars().all()

    return RecordListResponse(
        items=[_record_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{task_id}/records/{record_id}/restore",
    response_model=RecordResponse,
)
async def restore_task_record(
    task_id: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an excluded/unparsed row as restored (捞回).

    Honors 不删减: the row is never deleted — only ``status`` flips to
    ``restored`` so it drops out of the excluded view. This slice does NOT
    promote the row back to ``standard``; that workflow is deferred to a later
    slice. Returns the updated record.
    """
    await _load_owned_task(db, task_id, current_user)

    result = await db.execute(
        select(FlowRecordRow).where(
            FlowRecordRow.id == record_id,
            FlowRecordRow.task_id == task_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")

    row.status = "restored"
    db.add(
        TaskLog(
            task_id=task_id,
            level="info",
            message=f"Record restored: id={record_id} type={row.record_type}",
        )
    )
    await db.commit()
    await db.refresh(row)
    return _record_response(row)


@router.post("/{task_id}/cleaning/commit", response_model=TaskResponse)
async def commit_cleaning(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lock the current standard records as the downstream-usable snapshot.

    Writes a ``cleaning_committed`` ISO timestamp into ``task.config`` so the
    task can advance to the AI analysis stage. Does NOT re-run cleaning — the
    rule set is fixed (决策4), this only marks the snapshot.
    """
    task = await _load_owned_task(db, task_id, current_user)
    config = dict(task.config or {})
    config["cleaning_committed"] = datetime.now(timezone.utc).isoformat()
    task.config = config
    db.add(
        TaskLog(
            task_id=task_id,
            level="info",
            message="Cleaning committed (snapshot locked)",
        )
    )
    await db.commit()
    await db.refresh(task)
    return _task_response(task)


@router.get("/{task_id}/cleaning/export")
async def export_cleaning_log(
    task_id: int,
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export the unparsed + excluded cleaning log (with raw_payload + reason).

    Returns a downloadable CSV or JSON file. Every row carries its raw_payload
    (original cells) and exclude_reason so the cleaning decision is traceable
    and reversible (不删减).
    """
    await _load_owned_task(db, task_id, current_user)

    # selectinload Document so source_file (filename) is available without lazy
    # IO in the async loop. FlowRecordRow has no source_file column — the source
    # file name lives on the related Document.filename.
    result = await db.execute(
        select(FlowRecordRow)
        .options(selectinload(FlowRecordRow.document))
        .where(
            FlowRecordRow.task_id == task_id,
            FlowRecordRow.record_type.in_(["excluded", "unparsed"]),
        )
        .order_by(FlowRecordRow.id.asc())
    )
    rows = result.scalars().all()

    import json as _json

    if format == "json":
        payload = [_record_response(r).model_dump(mode="json") for r in rows]
        body = _json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(body),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="cleaning_log_{task_id}.json"'
            },
        )

    # CSV: one row per excluded/unparsed record, raw_payload serialized as JSON.
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "record_type",
            "status",
            "row_index",
            "source_file",
            "channel",
            "exclude_reason",
            "transaction_time",
            "counterparty_name",
            "amount",
            "raw_amount",
            "summary",
            "raw_payload",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.id,
                r.record_type,
                r.status,
                r.row_index,
                r.document.filename if r.document else "",
                r.channel or "",
                r.exclude_reason or "",
                r.transaction_time or "",
                r.counterparty_name or "",
                r.amount or "",
                r.raw_amount or "",
                r.summary or "",
                _json.dumps(r.raw_payload or {}, ensure_ascii=False),
            ]
        )
    body = buf.getvalue().encode("utf-8-sig")  # UTF-8 BOM so Excel reads CJK.
    return StreamingResponse(
        io.BytesIO(body),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="cleaning_log_{task_id}.csv"'
        },
    )

