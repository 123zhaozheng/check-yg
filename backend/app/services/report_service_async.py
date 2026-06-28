# -*- coding: utf-8 -*-
"""报告异步生成编排 service（06-28-report-fusion-word-cover Phase 2）.

模仿 ``analysis_service`` 的 background-job 模式：
* ``ReportGenerationService`` 单例 + ``_jobs: dict[int, asyncio.Task]`` 防重入。
* ``start_generation(db, task, user)``：建 ``Report(status="generating")`` + 8 个空
  ``ReportChapter(content="")`` → commit → **立即返回** report（status=generating）→
  起 background job（独立 ``async_session``）。
* ``_run_generation_job``：独立 session，逐章 ``run_chapter`` 填 content + 增量
  commit（前端轮询能渐进看到）；全完 → ``status="generated"``；整体失败 →
  ``status="failed"`` + log。

Report.status 扩展（DB 是 String 自由值，无需迁移）：
  * ``draft`` —— 已生成（旧值兼容，generated 的同义，前端都按可编辑处理）。
  * ``generating`` —— 生成中（前端轮询）。
  * ``generated`` —— 生成完成。
  * ``failed`` —— 生成失败。
  * ``final`` —— 定稿（整报告只读）。

复用（code-reuse-thinking-guide）：
* ``async_session``（app.database）—— background task 独立 session。
 * ``build_chapter_content``（report_chapter_builder）—— agent + 模板兜底。
* ``get_report_generation_model``（report_agent）—— 阶段卡片接线。
* ``notify_user``（app.websocket.notifications）—— WS 推进度。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.llm.report_agent import get_report_generation_model
from app.models import Report, ReportChapter, Task, TaskLog, User
from app.services.report_chapter_builder import (
    _aggregate,
    build_chapter_content,
    chapter_titles,
)
from app.websocket.notifications import notify_user

logger = logging.getLogger(__name__)

# 报告生成进度 WS 事件名。
_EVENT_REPORT_PROGRESS = "report.progress"

# 报告 status 值（DB 是 String 自由值，这里集中常量避免漂移）。
STATUS_DRAFT = "draft"
STATUS_GENERATING = "generating"
STATUS_GENERATED = "generated"
STATUS_FAILED = "failed"
STATUS_FINAL = "final"


class ReportGenerationService:
    """报告异步生成编排（模仿 analysis_service background-job 模式）。"""

    def __init__(self) -> None:
        # 生成 background job 跟踪（同 analysis_service，防重入）。
        self._jobs: dict[int, asyncio.Task] = {}

    def is_running(self, task_id: int) -> bool:
        """该任务是否正在生成报告。"""
        job = self._jobs.get(task_id)
        return bool(job and not job.done())

    async def start_generation(
        self, db: AsyncSession, task: Task, user: User
    ) -> Report:
        """启动异步报告生成。

        建 ``Report(status="generating")`` + 8 个空 ``ReportChapter(content="")`` →
        commit → 立即返回 report（status=generating）→ 起 background job。

        防重入：同 task 已在生成 → 抛 ValueError。

        Returns:
            新建的 Report（status=generating，带 8 个空章节）。
        """
        task_id = task.id
        if self.is_running(task_id):
            raise ValueError("报告正在生成中")

        # 在请求 session 里查 report_generation 阶段卡片（background 用独立 session）。
        report_model = await get_report_generation_model(db)

        # 建 Report(status=generating) + 8 个空章节（占位，background 逐章填）。
        content_path = f"report_chapters/task_{task_id}"
        report = Report(
            task_id=task_id,
            review_id=None,
            format="markdown",
            content_path=content_path,
            status=STATUS_GENERATING,
        )
        db.add(report)
        await db.flush()

        titles = chapter_titles()
        for idx, title in enumerate(titles):
            db.add(
                ReportChapter(
                    report_id=report.id,
                    title=title,
                    content="",
                    order_index=idx,
                )
            )

        db.add(
            TaskLog(
                task_id=task_id,
                level="info",
                message="Report generation started (8 chapters, LLM agent)",
            )
        )
        await db.commit()
        await db.refresh(report)

        # 起 background job（独立 session，逐章填 content）。
        job = asyncio.create_task(
            self._run_generation_job(
                task_id=task_id,
                report_id=report.id,
                owner_id=user.id,
                report_model=report_model,
            )
        )
        self._jobs[task_id] = job
        return report

    async def _run_generation_job(
        self,
        task_id: int,
        report_id: int,
        owner_id: int,
        report_model: Optional[object],
    ) -> None:
        """后台逐章 run_chapter 填 content + 增量 commit（前端轮询渐进看到）。

        全完 → Report.status="generated"；整体失败 → status="failed" + log。
        每章填完 WS 推进度（report.progress）。
        """
        total = len(chapter_titles())
        completed = 0
        succeeded = False
        try:
            async with async_session() as session:
                # 取 task + report（独立 session）。
                task = await session.get(Task, task_id)
                if task is None:
                    logger.error("报告生成 job：task %s 不存在", task_id)
                    return

                # 聚合一次真实数据，再逐章 LLM 生成；每章完成后立即写回，
                # 前端轮询能渐进看到已生成章节。
                agg = await _aggregate(session, task)
                result = await session.execute(
                    select(ReportChapter)
                    .where(ReportChapter.report_id == report_id)
                    .order_by(ReportChapter.order_index.asc())
                )
                chapters = list(result.scalars().all())

                for chapter in chapters:
                    chapter.content = await build_chapter_content(
                        session,
                        task,
                        chapter.order_index,
                        report_model=report_model,
                        agg=agg,
                    )
                    completed += 1
                    await session.commit()

                    await notify_user(
                        owner_id,
                        event=_EVENT_REPORT_PROGRESS,
                        title="报告生成进度",
                        message=f"已完成 {completed}/{total} 章",
                        resource={
                            "task_id": task_id,
                            "report_id": report_id,
                            "completed": completed,
                            "total": total,
                            "chapter_id": chapter.id,
                            "order_index": chapter.order_index,
                        },
                    )

                # 全完 → status=generated。
                report = await session.get(Report, report_id)
                if report is not None:
                    report.status = STATUS_GENERATED
                    session.add(
                        TaskLog(
                            task_id=task_id,
                            level="info",
                            message=(
                                f"Report generation finished: {completed}/{total} "
                                f"chapters"
                            ),
                        )
                    )
                    await session.commit()
                    succeeded = True
        except Exception as exc:
            logger.exception("报告生成 job %s 后台执行失败", task_id)
            async with async_session() as session:
                report = await session.get(Report, report_id)
                if report is not None:
                    report.status = STATUS_FAILED
                    session.add(
                        TaskLog(
                            task_id=task_id,
                            level="error",
                            message=f"Report generation failed: {exc}",
                        )
                    )
                    await session.commit()
            await notify_user(
                owner_id,
                event=_EVENT_REPORT_PROGRESS,
                title="报告生成失败",
                message=str(exc),
                resource={
                    "task_id": task_id,
                    "report_id": report_id,
                    "completed": completed,
                    "total": total,
                },
            )
        finally:
            self._jobs.pop(task_id, None)

        # 跑完最终通知。
        if succeeded:
            await notify_user(
                owner_id,
                event=_EVENT_REPORT_PROGRESS,
                title="报告生成完成",
                message=f"完成 {completed}/{total} 章",
                resource={
                    "task_id": task_id,
                    "report_id": report_id,
                    "completed": completed,
                    "total": total,
                },
            )


# 模块级单例（router 复用）。
report_generation_service = ReportGenerationService()
