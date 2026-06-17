# -*- coding: utf-8 -*-
"""Task management router."""

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..database import get_db
from ..models import Task, TaskLog, User
from ..services.extraction.runner import runner

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    document_folder: Optional[str] = None
    batch_size: int = 20
    confidence_threshold: int = 70


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
    )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List tasks with pagination and filters."""
    query = select(Task)

    if status_filter:
        query = query.where(Task.status == status_filter)
    if search:
        query = query.where(Task.title.contains(search))

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
    )
    db.add(task)
    await db.flush()
    db.add(TaskLog(task_id=task.id, level="info", message="Task created"))
    await db.commit()
    await db.refresh(task)
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


async def _load_owned_task(db: AsyncSession, task_id: int, current_user: User) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Task does not belong to current user")
    return task
