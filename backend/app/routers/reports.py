# -*- coding: utf-8 -*-
"""Report API router.

S7 章节化审查报告闭环：覆盖 ``POST /tasks/{task_id}/report`` 为章节化生成
（聚合 S5 flow_records + S6 findings(accepted) + 关键词审查(confirmed) +
余额校验(accepted) + Task 基础信息，按 8 章确定性模板拼装），
新增章节编辑/重生成/重排序 + 批注 + 定稿端点。

owner-only 校验：通过 ``Report.task_id`` → ``Task.owner_id == current_user.id``
（复用 ``tasks.py::_load_owned_task`` 模式）。定稿后写操作返 409（不删减精神：
只改 ``Report.status`` 软态，不改章节内容/不删行）。

旧 legacy ``ReportService`` 类保留不删（旧 ReviewMatch 报告链路本轮不再用，
但 ``GET /reports/{id}`` + download 仍走旧服务以兼容历史报告）。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import (
    Report,
    ReportAnnotation,
    ReportChapter,
    Task,
    User,
)
from app.schemas.review import (
    ReportAnnotationCreateRequest,
    ReportAnnotationResponse,
    ReportChapterPatchRequest,
    ReportChapterReorderItem,
    ReportChapterResponse,
    ReportResponse,
)
from app.llm.report_agent import get_report_generation_model
from app.services.report_chapter_builder import build_all_chapters, build_one_chapter
from app.services.report_service import ReportService, load_report
from app.services.report_service_async import (
    report_generation_service,
)
from app.websocket.notifications import notify_user

router = APIRouter(tags=["reports"])


# ---------------------------------------------------------------------------
# owner-only helpers
# ---------------------------------------------------------------------------


async def _load_owned_task(db: AsyncSession, task_id: int, current_user: User) -> Task:
    """复用 tasks.py::_load_owned_task 模式：404 unknown / 403 not owner."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Task does not belong to current user")
    return task


async def _load_owned_report(
    db: AsyncSession, report_id: int, current_user: User
) -> Report:
    """加载 report + owner 校验（通过 report.task_id → Task.owner_id）."""
    result = await db.execute(
        select(Report)
        .options(
            selectinload(Report.chapters),
            selectinload(Report.annotations),
        )
        .where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    task_result = await db.execute(select(Task).where(Task.id == report.task_id))
    task = task_result.scalar_one_or_none()
    if not task or task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Report does not belong to current user")
    return report


def _ensure_draft(report: Report) -> None:
    """写操作守卫：final/generating 时返 409.

    允许 draft / generated / failed 态编辑。generating 后台逐章写回，前端只轮询
    查看，避免人工编辑与后台生成互相覆盖。
    """
    if report.status == "final":
        raise HTTPException(
            status_code=409, detail="Report is finalized and read-only"
        )
    if report.status == "generating":
        raise HTTPException(
            status_code=409, detail="Report is still generating"
        )


def _chapter_response(ch: ReportChapter) -> ReportChapterResponse:
    return ReportChapterResponse(
        id=ch.id,
        report_id=ch.report_id,
        title=ch.title,
        content=ch.content,
        order_index=ch.order_index,
        generated_at=ch.generated_at,
    )


def _annotation_response(a: ReportAnnotation) -> ReportAnnotationResponse:
    return ReportAnnotationResponse(
        id=a.id,
        report_id=a.report_id,
        chapter_id=a.chapter_id,
        author=a.author,
        content=a.content,
        resolved=a.resolved,
        created_at=a.created_at,
    )


def _report_response(report: Report) -> ReportResponse:
    """组装 ReportResponse（含按 order_index 排序的 chapters + annotations）."""
    chapters = sorted(report.chapters, key=lambda c: c.order_index)
    return ReportResponse(
        id=report.id,
        task_id=report.task_id,
        review_id=report.review_id,
        format=report.format,
        content_path=report.content_path,
        content="",
        status=report.status,
        chapters=[_chapter_response(c) for c in chapters],
        annotations=[_annotation_response(a) for a in report.annotations],
        created_at=report.created_at,
    )


# ---------------------------------------------------------------------------
# S7 章节化生成 + 读取
# ---------------------------------------------------------------------------


@router.post("/tasks/{task_id}/report", response_model=ReportResponse)
async def generate_task_report(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """章节化异步生成报告（06-28 Phase 2：LLM agent，每章一个 run）.

    立即建 ``Report(status="generating")`` + 8 个空 ``ReportChapter`` → 返回
    generating → 后台逐章 ``run_chapter`` 填 content + 增量 commit。
    前端轮询 GET report 直到 status=generated/failed。

    幂等：task 已有报告（任意状态）则返已有。正在生成中（generating）也返已有
    （前端继续轮询）。
    """
    task = await _load_owned_task(db, task_id, current_user)

    # 幂等：已有任意状态报告则返回（generating/draft/generated 可继续，final 只读）。
    existing = (
        await db.execute(
            select(Report)
            .options(selectinload(Report.chapters), selectinload(Report.annotations))
            .where(Report.task_id == task.id)
            .order_by(Report.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return _report_response(existing)

    # 防重入：同 task 已在生成（理论上 existing 会命中，双保险）。
    if report_generation_service.is_running(task.id):
        raise HTTPException(status_code=409, detail="报告正在生成中")

    # 异步生成：建 generating report + 8 空章 → 立即返回 → 后台逐章填。
    report = await report_generation_service.start_generation(db, task, current_user)

    # 重新加载带 relationships 的 report（start_generation 返回的 report 可能
    # 没有 selectinload 的 chapters）。
    loaded = (
        await db.execute(
            select(Report)
            .options(selectinload(Report.chapters), selectinload(Report.annotations))
            .where(Report.id == report.id)
        )
    ).scalar_one()

    await notify_user(
        current_user.id,
        event="report.progress",
        title="报告开始生成",
        message=f"任务 {task.id} 报告开始生成（8 章 LLM agent）。",
        resource={"task_id": task.id, "report_id": loaded.id},
    )
    return _report_response(loaded)


@router.get("/tasks/{task_id}/report", response_model=ReportResponse)
async def get_task_report(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取该 task 当前报告 + chapters（按 order_index 排序）+ annotations."""
    await _load_owned_task(db, task_id, current_user)
    report = (
        await db.execute(
            select(Report)
            .options(selectinload(Report.chapters), selectinload(Report.annotations))
            .where(Report.task_id == task_id)
            .order_by(Report.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return _report_response(report)


# ---------------------------------------------------------------------------
# S7 章节编辑 / 重生成 / 重排序
# ---------------------------------------------------------------------------


@router.patch(
    "/reports/{report_id}/chapters/{chapter_id}",
    response_model=ReportChapterResponse,
)
async def patch_chapter(
    report_id: int,
    chapter_id: int,
    request: ReportChapterPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑章节 content（纯文本 Markdown，定稿 409）."""
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)

    chapter = next((c for c in report.chapters if c.id == chapter_id), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter.content = request.content
    await db.commit()
    await db.refresh(chapter)
    return _chapter_response(chapter)


@router.post(
    "/reports/{report_id}/chapters/{chapter_id}/regenerate",
    response_model=ReportChapterResponse,
)
async def regenerate_chapter(
    report_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """单章重生成（LLM agent run_chapter，失败回退模板，定稿 409）.

    走 ``build_one_chapter``（agent.run + 模板兜底）。单章同步可接受（1 次 LLM 调用）。
    """
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)

    chapter = next((c for c in report.chapters if c.id == chapter_id), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    task_result = await db.execute(select(Task).where(Task.id == report.task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    report_model = await get_report_generation_model(db)
    chapter.content = await build_one_chapter(
        db, task, chapter.order_index, report_model=report_model
    )
    await db.commit()
    await db.refresh(chapter)
    return _chapter_response(chapter)


@router.post(
    "/reports/{report_id}/chapters/reorder",
    response_model=ReportResponse,
)
async def reorder_chapters(
    report_id: int,
    items: list[ReportChapterReorderItem],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拖拽排序：body ``[{chapter_id, order_index}, ...]`` 批量更新（定稿 409）."""
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)

    by_id = {c.id: c for c in report.chapters}
    for item in items:
        chapter = by_id.get(item.chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        chapter.order_index = item.order_index
    await db.commit()

    # 重新加载带 relationships。
    loaded = (
        await db.execute(
            select(Report)
            .options(selectinload(Report.chapters), selectinload(Report.annotations))
            .where(Report.id == report.id)
        )
    ).scalar_one()
    return _report_response(loaded)


@router.post("/reports/{report_id}/regenerate", response_model=ReportResponse)
async def regenerate_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全报告重生成（LLM agent build_all_chapters，失败逐章回退模板，定稿 409）.

    重生成重写 content（派生数据再生），不改 order_index / 不删行——
    原始记录在 S5 flow_records.raw_payload 已兜底（不删减精神）。
    """
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)

    task_result = await db.execute(select(Task).where(Task.id == report.task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    report_model = await get_report_generation_model(db)
    contents = await build_all_chapters(db, task, report_model=report_model)
    for idx, chapter in enumerate(sorted(report.chapters, key=lambda c: c.order_index)):
        if idx < len(contents):
            chapter.content = contents[idx]
    await db.commit()

    loaded = (
        await db.execute(
            select(Report)
            .options(selectinload(Report.chapters), selectinload(Report.annotations))
            .where(Report.id == report.id)
        )
    ).scalar_one()
    return _report_response(loaded)


# ---------------------------------------------------------------------------
# S7 批注
# ---------------------------------------------------------------------------


@router.post(
    "/reports/{report_id}/annotations",
    response_model=ReportAnnotationResponse,
)
async def create_annotation(
    report_id: int,
    request: ReportAnnotationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建批注（chapter_id + content + author=current_user.username，定稿 409）."""
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)

    if request.chapter_id is not None:
        if not any(c.id == request.chapter_id for c in report.chapters):
            raise HTTPException(status_code=404, detail="Chapter not found")

    annotation = ReportAnnotation(
        report_id=report.id,
        chapter_id=request.chapter_id,
        author=current_user.username,
        content=request.content,
        resolved=False,
    )
    db.add(annotation)
    await db.commit()
    await db.refresh(annotation)
    return _annotation_response(annotation)


@router.patch(
    "/reports/{report_id}/annotations/{annotation_id}",
    response_model=ReportAnnotationResponse,
)
async def toggle_annotation(
    report_id: int,
    annotation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换批注 resolved 状态（定稿 409）."""
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)

    annotation = next(
        (a for a in report.annotations if a.id == annotation_id), None
    )
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    annotation.resolved = not annotation.resolved
    await db.commit()
    await db.refresh(annotation)
    return _annotation_response(annotation)


# ---------------------------------------------------------------------------
# S7 定稿
# ---------------------------------------------------------------------------


@router.post("/reports/{report_id}/finalize", response_model=ReportResponse)
async def finalize_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """定稿：Report.status → final（章节只读，后续编辑/重生成/批注新建均 409）.

    不删减精神：定稿不改章节内容、不删行，只改 ``Report.status`` 软态。
    """
    report = await _load_owned_report(db, report_id, current_user)
    _ensure_draft(report)
    report.status = "final"
    await db.commit()

    loaded = (
        await db.execute(
            select(Report)
            .options(selectinload(Report.chapters), selectinload(Report.annotations))
            .where(Report.id == report.id)
        )
    ).scalar_one()
    return _report_response(loaded)


# ---------------------------------------------------------------------------
# Legacy: GET /reports/{id} + download (旧 ReviewMatch 链路兼容)
# 旧 ReportService 类保留不删；新章节化报告走上面的 S7 端点。
# ---------------------------------------------------------------------------


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get report metadata and content (legacy: 旧 ReviewMatch 报告兼容读取)."""
    report = await load_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    task_result = await db.execute(select(Task).where(Task.id == report.task_id))
    task = task_result.scalar_one_or_none()
    if not task or task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Report does not belong to current user")

    content = await ReportService().read_report_content(report)
    # 旧报告无 chapters/annotations，返回空列表 + status（旧报告默认 draft）。
    return ReportResponse(
        id=report.id,
        task_id=report.task_id,
        review_id=report.review_id,
        format=report.format,
        content_path=report.content_path,
        content=content,
        status=getattr(report, "status", "draft"),
        chapters=[],
        annotations=[],
        created_at=report.created_at,
    )


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download generated report file (legacy)."""
    report = await load_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    task_result = await db.execute(select(Task).where(Task.id == report.task_id))
    task = task_result.scalar_one_or_none()
    if not task or task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Report does not belong to current user")

    path = Path(report.content_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(path, filename=path.name, media_type="text/markdown; charset=utf-8")
