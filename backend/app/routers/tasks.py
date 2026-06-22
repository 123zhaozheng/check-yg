# -*- coding: utf-8 -*-
"""Task management router."""

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Task, TaskLog, User
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


async def _save_uploads(files: List[UploadFile], dest_dir: Path) -> Path:
    """Persist uploaded files to dest_dir, keeping only supported extensions.

    Returns dest_dir if at least one supported file was saved, else raises 422.
    """
    saved = 0
    for upload in files:
        filename = upload.filename or ""
        if not is_supported_upload_name(filename):
            continue
        safe_name = Path(filename).name
        if not safe_name:
            continue
        dest = dest_dir / safe_name
        with open(dest, "wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        saved += 1
    if saved == 0:
        raise HTTPException(
            status_code=422,
            detail="No supported files uploaded (expected .pdf/.docx/.xlsx/.xls)",
        )
    return dest_dir


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
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a task from uploaded files and start extraction immediately.

    Files are saved under a per-task upload subfolder, which becomes the
    extraction ``document_folder`` — no backend-local directory path is typed
    by the user.
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
    await _save_uploads(files, upload_dir)
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
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append uploaded documents to an existing task and start append extraction.

    Files land in a fresh per-run subfolder so same-named files from different
    append runs stay distinct (path-aware document identity).
    """
    task = await _load_owned_task(db, task_id, current_user)
    if task.status == "running" or runner.is_running(task.id):
        raise HTTPException(status_code=409, detail="Task is already running")
    _ensure_supported_files(files)

    config = dict(task.config or {})
    upload_dir = _next_upload_run_dir(task.id, config)
    await _save_uploads(files, upload_dir)

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
