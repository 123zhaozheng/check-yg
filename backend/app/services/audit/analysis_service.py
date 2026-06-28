# -*- coding: utf-8 -*-
"""AI 审查分析 + 追问会话 service（06-26-ai-agent）.

* ``run_analysis(db, task_id, user)`` —— 异步 background task，串行跑所有 enabled
  维度。**重跑策略（PRD §七 Q5）：先删 ``status='pending'`` 的 finding，保留
  accepted/ignored 人工结论**（呼应「清洗不删减」硬底线）。每跑完一个维度 →
  落一条聚合 finding（detail_text + evidence_record_ids + dimension_id +
  source='rule'）+ 通过 WebSocket 推进度（event=``analysis.progress``）。零命中
  不建 finding。单维度失败 try/except 跳过 + log（容错 spec）。最后写
  ``task.config.last_analysis_at``。
* ``chat(db, task_id, conversation_id, user_msg, user)`` —— 读
  ``AuditConversation.message_history`` → 追问 agent.run(msg, message_history) →
  序列化新 history 存回 → 返 reply。首轮流建会话（title=首问题前 10 字）。

复用（code-reuse-thinking-guide）：
* ``run_dimension`` / ``chat``（app.llm.analysis）—— 真 agent.run，不重写。
* ``notify_user``（app.websocket.notifications）—— WS 推进度。
* ``async_session``（app.database）—— background task 独立 session。
* ``get_analysis_model`` / ``get_ai_qa_model`` —— 阶段卡片接线。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.llm.analysis import (
    AuditDeps,
    chat as agent_chat,
    extract_history_messages,
    get_ai_qa_model,
    get_analysis_model,
    run_dimension,
)
from app.models import AuditConversation, AuditDimension, Finding, Task, TaskLog, User
from app.websocket.notifications import notify_user

logger = logging.getLogger(__name__)


# 分析进度 WS 事件名（PRD §五/§一）。
_EVENT_ANALYSIS_PROGRESS = "analysis.progress"


class AnalysisService:
    """AI 审查分析 + 追问会话编排。"""

    def __init__(self) -> None:
        # 跑分析 background job 跟踪（同 runner 模式，防重入）。
        self._jobs: dict[int, asyncio.Task] = {}

    def is_running(self, task_id: int) -> bool:
        """该任务是否正在跑分析。"""
        job = self._jobs.get(task_id)
        return bool(job and not job.done())

    async def start_analysis(
        self, db: AsyncSession, task_id: int, user: User
    ) -> None:
        """启动异步分析（background task）。立即返回，后台串行跑 enabled 维度。

        重跑策略：先删该任务 ``status='pending'`` 的 finding（保留
        accepted/ignored 人工结论）。每跑完一个维度 → 落聚合 finding + WS 推进度。
        单维度失败 try/except 跳过 + log。最后写 ``task.config.last_analysis_at``。
        """
        if self.is_running(task_id):
            raise ValueError("分析正在运行中")

        # 取 enabled 维度（在请求 session 里查，避免 background session 时序问题）。
        dims_result = await db.execute(
            select(AuditDimension)
            .where(AuditDimension.enabled.is_(True))
            .order_by(AuditDimension.id.asc())
        )
        dimensions = list(dims_result.scalars().all())

        # 重跑策略：删 pending finding（保留人工结论）。在请求 session 里删 + 提交，
        # background task 用独立 session 跑维度。
        await db.execute(
            delete(Finding).where(
                Finding.task_id == task_id,
                Finding.status == "pending",
            )
        )
        config = dict((await db.get(Task, task_id)).config or {})
        config["last_analysis_at"] = datetime.now(timezone.utc).isoformat()
        # 记录本次跑的维度数 + 摘要占位（background 跑完回填）。
        config["last_analysis_summary"] = {
            "total_dimensions": len(dimensions),
            "completed": 0,
            "findings": 0,
            "status": "running",
        }
        task = await db.get(Task, task_id)
        task.config = config
        db.add(
            TaskLog(
                task_id=task_id,
                level="info",
                message=f"AI analysis started: {len(dimensions)} dimensions",
            )
        )
        await db.commit()

        # 阶段卡片在请求 session 查（background session 也行，但一次查完更稳）。
        analysis_model = await get_analysis_model(db)

        job = asyncio.create_task(
            self._run_analysis_job(
                task_id=task_id,
                owner_id=user.id,
                dimensions=dimensions,
                analysis_model=analysis_model,
            )
        )
        self._jobs[task_id] = job

    async def _run_analysis_job(
        self,
        task_id: int,
        owner_id: int,
        dimensions: list[AuditDimension],
        analysis_model: Optional[Any],
    ) -> None:
        """后台串行跑每个 enabled 维度，每跑完一个落聚合 finding + WS 推进度。

        每跑完一个维度**增量写** ``task.config.last_analysis_summary``（PRD §十一
        进度条按「已完成维度数/总维度数」走——验收项，非可选）：``{total, completed,
        status, findings}``。开始时 ``status=running/completed=0``，每维度完 ``completed++``
        并落库，跑完写 ``status=finished``。前端读此字段渲染进度条，不再不定式。
        """
        total = len(dimensions)
        completed = 0
        new_findings_count = 0
        summaries: list[str] = []
        try:
            async with async_session() as session:
                deps = AuditDeps(db=session, task_id=task_id, user_id=owner_id)
                for dim in dimensions:
                    try:
                        result = await run_dimension(deps, dim, model=analysis_model)
                        completed += 1
                        # 落聚合 finding：result.findings 非空 → 取第一条（一次维度
                        # 运行产出一条聚合 finding，PRD §五 Q2）。
                        for item in result.findings:
                            finding = Finding(
                                task_id=task_id,
                                type=item.type,
                                severity=item.severity,
                                description=item.detail_text,  # 详情正文也进 description
                                counterparty=item.counterparty,
                                amount=item.amount,
                                confidence=item.confidence,
                                status="pending",
                                dimension_id=dim.id,
                                detail_text=item.detail_text,
                                evidence_record_ids=list(item.evidence_record_ids or []),
                                source="rule",
                            )
                            session.add(finding)
                            new_findings_count += 1
                        if not result.findings:
                            summaries.append(f"{dim.name}：未发现异常")
                        else:
                            summaries.append(f"{dim.name}：{result.summary or '命中'}")
                        await session.commit()
                    except Exception as exc:
                        # 单维度失败 → 跳过 + log，不阻塞其他（容错 spec）。
                        # 失败也算「跑过」推进度（completed++），否则前端进度条卡住。
                        completed += 1
                        logger.warning(
                            "维度「%s」(id=%s) 跑分析失败，跳过: %s",
                            dim.name,
                            dim.id,
                            exc,
                        )
                        summaries.append(f"{dim.name}：分析失败（{exc}）")

                    # 每跑完一个维度 → 增量写 last_analysis_summary（completed 推进）+
                    # WS 推进度。task.config 是 jsonb，拷贝再写回（现有模式）。
                    task_cfg = await session.get(Task, task_id)
                    if task_cfg is not None:
                        cfg = dict(task_cfg.config or {})
                        cfg["last_analysis_summary"] = {
                            "total_dimensions": total,
                            "completed": completed,
                            "findings": new_findings_count,
                            "status": "running",
                        }
                        task_cfg.config = cfg
                        await session.commit()

                    await notify_user(
                        owner_id,
                        event=_EVENT_ANALYSIS_PROGRESS,
                        title="分析进度",
                        message=f"已完成 {completed}/{total} 个维度",
                        resource={
                            "task_id": task_id,
                            "completed": completed,
                            "total": total,
                            "new_findings": new_findings_count,
                            "dimension_name": dim.name,
                        },
                    )

                # 写 last_analysis_at + 摘要回填。
                task = await session.get(Task, task_id)
                if task is not None:
                    cfg = dict(task.config or {})
                    cfg["last_analysis_at"] = datetime.now(timezone.utc).isoformat()
                    cfg["last_analysis_summary"] = {
                        "total_dimensions": total,
                        "completed": completed,
                        "findings": new_findings_count,
                        "status": "finished",
                        "details": summaries,
                    }
                    task.config = cfg
                    session.add(
                        TaskLog(
                            task_id=task_id,
                            level="info",
                            message=(
                                f"AI analysis finished: {completed}/{total} dims, "
                                f"{new_findings_count} findings"
                            ),
                        )
                    )
                    await session.commit()
        except Exception as exc:
            logger.exception("分析任务 %s 后台执行失败", task_id)
            async with async_session() as session:
                task = await session.get(Task, task_id)
                if task is not None:
                    session.add(
                        TaskLog(
                            task_id=task_id,
                            level="error",
                            message=f"AI analysis failed: {exc}",
                        )
                    )
                    await session.commit()
            await notify_user(
                owner_id,
                event=_EVENT_ANALYSIS_PROGRESS,
                title="分析失败",
                message=str(exc),
                resource={"task_id": task_id, "completed": completed, "total": total},
            )
        finally:
            self._jobs.pop(task_id, None)

        # 跑完最终通知。
        await notify_user(
            owner_id,
            event=_EVENT_ANALYSIS_PROGRESS,
            title="分析完成",
            message=f"完成 {completed}/{total} 个维度，新增 {new_findings_count} 条发现",
            resource={
                "task_id": task_id,
                "completed": completed,
                "total": total,
                "new_findings": new_findings_count,
            },
        )

    # ------------------------------------------------------------------
    # 追问会话
    # ------------------------------------------------------------------

    async def list_conversations(
        self, db: AsyncSession, task_id: int
    ) -> list[dict]:
        """列出任务的所有追问会话（按 id 升序）。返 ``[{id, title, created_at, updated_at}]``。"""
        result = await db.execute(
            select(AuditConversation)
            .where(AuditConversation.task_id == task_id)
            .order_by(AuditConversation.id.asc())
        )
        return [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in result.scalars().all()
        ]

    async def get_conversation(
        self, db: AsyncSession, task_id: int, conversation_id: int
    ) -> dict:
        """取单个追问会话 + 抽取后的可读消息历史。

        ``message_history`` 存的是 pydantic-ai ModelMessages（JSON）。序列化后用
        ``extract_history_messages`` 抽成 ``[{role, text}]``（user/ai 文本），
        供前端点历史会话时回放到聊天面板。校验会话属于该任务。
        """
        result = await db.execute(
            select(AuditConversation).where(
                AuditConversation.id == conversation_id,
                AuditConversation.task_id == task_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise LookupError("Conversation not found")

        import json as _json

        history_json: Optional[str] = None
        if conv.message_history:
            try:
                history_json = _json.dumps(conv.message_history, ensure_ascii=False)
            except (TypeError, ValueError):
                history_json = None

        return {
            "id": conv.id,
            "title": conv.title,
            "messages": extract_history_messages(history_json),
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
        }

    async def create_conversation(
        self, db: AsyncSession, task_id: int, title: str
    ) -> AuditConversation:
        """新建追问会话（title=首问题前 10 字，由 router 传入）。"""
        conv = AuditConversation(
            task_id=task_id,
            title=(title or "")[:100],
            message_history=[],
        )
        db.add(conv)
        await db.flush()
        logger.info("新建追问会话: id=%s task=%s title=%s", conv.id, task_id, conv.title)
        return conv

    async def delete_conversation(
        self, db: AsyncSession, task_id: int, conversation_id: int
    ) -> None:
        """删会话（只删对话历史，不影响已沉淀维度——沉淀落 audit_dimensions，跟会话独立）。

        校验会话属于该任务。
        """
        result = await db.execute(
            select(AuditConversation).where(
                AuditConversation.id == conversation_id,
                AuditConversation.task_id == task_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise LookupError("Conversation not found")
        await db.delete(conv)
        logger.info("删除追问会话: id=%s task=%s", conversation_id, task_id)

    async def chat(
        self,
        db: AsyncSession,
        task_id: int,
        conversation_id: Optional[int],
        user_msg: str,
        user: User,
    ) -> tuple[int, str, list[dict], Optional[dict]]:
        """追问：取/建会话 → agent.run(msg, message_history) → 存回 → 返
        (conv_id, reply, tool_traces, sedimented_dimension)。

        ``conversation_id`` 为 None 时新建会话（title=首问题前 10 字）。
        ``tool_traces`` / ``sedimented_dimension`` 透传自 ``agent_chat`` 的
        ChatResult（PRD §十：前端气泡显工具痕迹 + 沉淀草稿标记）。
        """
        # 取或建会话。
        if conversation_id is not None:
            result = await db.execute(
                select(AuditConversation).where(
                    AuditConversation.id == conversation_id,
                    AuditConversation.task_id == task_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv is None:
                raise LookupError("Conversation not found")
        else:
            title = (user_msg or "")[:10]
            conv = AuditConversation(
                task_id=task_id,
                title=title,
                message_history=[],
            )
            db.add(conv)
            await db.flush()

        # 反序列化旧 history。
        history_json: Optional[str] = None
        if conv.message_history:
            import json as _json

            try:
                history_json = _json.dumps(conv.message_history, ensure_ascii=False)
            except (TypeError, ValueError):
                history_json = None

        deps = AuditDeps(db=db, task_id=task_id, user_id=user.id)
        qa_model = await get_ai_qa_model(db)
        chat_result = await agent_chat(
            deps, history_json, user_msg, model=qa_model
        )

        # 序列化新 history 存回。
        import json as _json2

        try:
            conv.message_history = _json2.loads(chat_result.new_history_json)
        except (TypeError, ValueError):
            # 保留旧 history，不覆盖。
            pass
        conv.title = conv.title or (user_msg or "")[:10]

        # 记当前激活会话到 task.config.active_conversation_id（PRD §八/§九，
        # 前端悬浮球据此高亮当前会话；后端无业务依赖，纯前端便利）。
        task = await db.get(Task, task_id)
        if task is not None:
            cfg = dict(task.config or {})
            cfg["active_conversation_id"] = conv.id
            task.config = cfg

        await db.commit()
        tool_traces = [t.model_dump() for t in chat_result.tool_traces]
        sedimented = (
            chat_result.sedimented_dimension.model_dump()
            if chat_result.sedimented_dimension is not None
            else None
        )
        return conv.id, chat_result.reply, tool_traces, sedimented


# 模块级单例（router 复用）。
analysis_service = AnalysisService()
