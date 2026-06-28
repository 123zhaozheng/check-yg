# -*- coding: utf-8 -*-
"""AI 审查 agent —— 维度跑分析 + 悬浮追问（06-26-ai-agent）.

核心范式（PRD §一）：**维度 = 结构化提示词**（不是工具、不是代码规则）；一套
固化的只读表访问工具被所有维度共享；跑分析 = 每个 enabled 维度各跑一次
agentic ``agent.run``；追问 = 悬浮框多轮对话；沉淀 = ``create_dimension`` 工具
填字段 → 服务端拼模板 → 落库。新维度沉淀零代码。

落地严格遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)：
* ``AuditDeps`` dataclass：``db: AsyncSession`` + ``task_id: int`` + ``user_id: int``
  （user_id 供 create_dimension 落 created_by）。
* 5 个只读工具用 ``FunctionToolset`` 打包成 ``ReadAuditToolset``（两 agent 共享）。
  底层查 ``flow_records WHERE task_id=? AND record_type='standard'``，金额/时间
  解析复用 ``app.services.audit.parsing``（legacy ``_parse_amount``/``_parse_datetime``）。
  所有工具带 limit（明细默认 200，硬上限 1000）防爆 context。
* 维度 agent：``output_type=DimensionFindingResult``，instructions=该维度 prompt
  （动态），挂 ``ReadAuditToolset``，agentic 单次 run 内多步工具循环，阶段卡
  ``STAGE_AI_ANALYSIS``。
* 追问 agent：``output_type=str``，instructions=静态通用 QA，挂 ``ReadAuditToolset``
  + ``query_findings`` + ``create_dimension``，阶段卡 ``STAGE_AI_QA``，多轮走
  ``message_history`` + ``ModelMessagesTypeAdapter``。
* 复用 ``agent_factory.get_agent``（模块级单例，缓存 key 含 instructions → 每个
  维度 prompt 各自一个缓存 agent 单例）。
* ``create_dimension`` 限 ``steps.tool`` 白名单（5 个只读 + query_findings），
  编造 → ``ModelRetry``；服务端拼 prompt 落 ``AuditDimension``（source=agent,
  enabled=false, created_by=当前用户）。**agent 无删除工具**。

硬底线（不删减）：只读工具不改任何记录；重跑只删 pending finding 保留人工结论
（在 service 层）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    ModelMessagesTypeAdapter,
    ModelRetry,
    RunContext,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.toolsets import FunctionToolset
from pydantic_core import to_json
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.agent_factory import get_agent
from app.llm.types import DimensionFindingResult
from app.models import AuditDimension, Finding, FlowRecordRow
from app.models.audit_dimension import DIMENSION_SEVERITIES, SOURCE_AGENT
from app.models.llm_model import LLMModel
from app.models.llm_model_assignment import STAGE_AI_ANALYSIS, STAGE_AI_QA
from app.services.audit.dimension_prompt import build_dimension_prompt
from app.services.audit.parsing import parse_amount, parse_datetime
from app.services.llm_model_service import get_stage_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deps — per-request 数据走 deps=（conventions.md：deps_type 传类型，deps= 传实例）
# ---------------------------------------------------------------------------


@dataclass
class AuditDeps:
    """per-request deps for the audit agents (conventions.md).

    ``user_id`` 供 ``create_dimension`` 落 ``created_by``（追问 agent 沉淀维度时）。
    """

    db: AsyncSession
    task_id: int
    user_id: int


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 明细类工具默认 / 硬上限 limit（PRD §二，防爆 context）。
_DEFAULT_DETAIL_LIMIT = 200
_HARD_DETAIL_LIMIT = 1000

# 只读工具白名单 —— create_dimension 的 steps.tool 限此集合 + query_findings。
READONLY_TOOL_WHITELIST = frozenset(
    {
        "get_task_summary",
        "query_by_time",
        "query_by_amount",
        "query_by_counterparty",
        "query_burst",
        "query_findings",
    }
)

# 追问 agent 静态通用 QA instructions（多轮；挂只读 Toolset + query_findings +
# create_dimension）。
_QA_INSTRUCTIONS = """你是银行/支付流水审计问答助手（悬浮追问）。

## 任务
针对当前审查任务的标准化流水，回答审计人员的追问。可调用只读查询工具获取真实
数据，不要编造。回答要先给结论，再补充依据；引用记录时带上对手名、金额、交易
时间、流水行号等可追溯信息。

## 可用工具（只读，已剔除无时分秒记录，均带limit防爆context）
- get_task_summary / query_by_time / query_by_amount / query_by_counterparty /
  query_burst：查标准化流水（standard 记录）。
- query_findings：查本任务已有的异常发现（findings）。
- create_dimension：当审计人员在追问中提出一个**新的、可复用的审查维度**时，
  调此工具沉淀它（填 name/purpose/steps/judgment/severity）。日常问答不要调。

## 沉淀维度（create_dimension）
仅当审计人员明确说「沉淀/保存/加成一个维度」时才调 create_dimension。steps.tool
限白名单（上述只读工具 + query_findings），不要编造工具名。沉淀出的维度是草稿
（enabled=false），需人在维度管理页启用才进 analyze。

## 输出
纯文本回答。若上下文不足以回答，明确说明「根据当前数据无法确定」，并说明缺了什么。
"""

_MAX_TOKENS_DIMENSION = 4000
_MAX_TOKENS_QA = 2000


# ---------------------------------------------------------------------------
# 阶段模型卡片接线（STAGE_AI_ANALYSIS / STAGE_AI_QA）
# ---------------------------------------------------------------------------


async def get_analysis_model(db: AsyncSession) -> Optional[LLMModel]:
    """ai_analysis 阶段指派的卡片（维度跑分析用）。未指派返 None → 回退 env settings。"""
    return await get_stage_model(db, STAGE_AI_ANALYSIS)


async def get_ai_qa_model(db: AsyncSession) -> Optional[LLMModel]:
    """ai_qa 阶段指派的卡片（追问 agent 用）。未指派返 None → 回退 env settings。"""
    return await get_stage_model(db, STAGE_AI_QA)


def _resolve_agent_params(
    model: Optional[LLMModel], *, fallback_max_tokens: int
) -> dict[str, Any]:
    """解析 agent 连接参数（优先级：阶段卡片 > env settings > 模块常量）。

    对齐 extractor ``_resolve_stage_llm_params``：卡片字段空时回退 env settings。
    ``thinking``：卡片是 reasoning 且 default_thinking≠off 时传 low/medium/high；
    否则 None（不给非 reasoning 模型发 reasoning_effort，research §3）。
    """
    env_base_url = settings.LLM_API_ENDPOINT
    env_api_key = settings.LLM_API_KEY
    env_model = settings.LLM_MODEL_NAME
    env_timeout = settings.LLM_TIMEOUT

    if model is None:
        return {
            "base_url": None,  # None → get_agent 回退 env settings
            "api_key": None,
            "model": None,
            "timeout": None,
            "max_tokens": fallback_max_tokens,
            "thinking": None,
            "temperature": None,
        }

    thinking = model.default_thinking
    if thinking == "off" or not model.is_reasoning:
        thinking = None
    return {
        "base_url": model.provider_base_url or None,
        "api_key": model.api_key or None,
        "model": model.model_name or None,
        "timeout": None,  # timeout 不来自卡片，用 env settings
        "max_tokens": model.default_max_tokens or fallback_max_tokens,
        "thinking": thinking,
        "temperature": model.default_temperature,
    }


# ---------------------------------------------------------------------------
# 只读工具 —— 行→dict 快照 + 5 个工具（FunctionToolset 打包）
# ---------------------------------------------------------------------------


def _row_to_dict(row: FlowRecordRow) -> dict:
    """精简 flow_records 行为 dict 供 agent 工具返回（只读快照）。"""
    return {
        "id": row.id,
        "channel": row.channel,
        "transaction_time": row.transaction_time,
        "counterparty_name": row.counterparty_name,
        "counterparty_account": row.counterparty_account,
        "amount": row.amount,
        "raw_amount": row.raw_amount,
        "summary": row.summary,
        "transaction_type": row.transaction_type,
    }


def _has_hms(tx_time: Optional[str]) -> bool:
    """交易时间是否带非零时分秒（剔除「只记日期」噪音，PRD §二）。

    ``00:00:00`` 视为「只记日期」噪音（不可关）。带时分秒且非全 0 → True。
    """
    if not tx_time:
        return False
    # 形如 "YYYY-MM-DD HH:MM:SS" / "YYYY-MM-DDTHH:MM:SS"。
    parts = tx_time.replace("T", " ").split(" ", 1)
    if len(parts) != 2:
        return False
    hms = parts[1].strip()
    if not hms:
        return False
    # 全 0（00:00:00 / 00:00）→ 噪音。
    return any(ch != "0" and ch != ":" for ch in hms)


def _clamp_limit(limit: int | None) -> int:
    """limit 夹到 [1, _HARD_DETAIL_LIMIT]。"""
    if limit is None:
        return _DEFAULT_DETAIL_LIMIT
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return _DEFAULT_DETAIL_LIMIT
    if n < 1:
        return 1
    if n > _HARD_DETAIL_LIMIT:
        return _HARD_DETAIL_LIMIT
    return n


async def _load_standard_rows(db: AsyncSession, task_id: int) -> list[FlowRecordRow]:
    """取该 task 所有 standard flow_records（按 id 升序）。"""
    result = await db.execute(
        select(FlowRecordRow)
        .where(
            FlowRecordRow.task_id == task_id,
            FlowRecordRow.record_type == "standard",
        )
        .order_by(FlowRecordRow.id.asc())
    )
    return list(result.scalars().all())


def build_read_audit_toolset() -> FunctionToolset[AuditDeps]:
    """构造 5 个只读工具打包的 ``FunctionToolset``（两 agent 共享）。

    每个工具 docstring 成工具描述，参数成 JSON schema（conventions.md）。
    所有工具底层查 ``flow_records WHERE task_id=? AND record_type='standard'``，
    金额/时间解析复用 ``app.services.audit.parsing``。明细类带 limit（默认 200，
    硬上限 1000）。**只读不改**（不删减底线）。
    """

    toolset: FunctionToolset[AuditDeps] = FunctionToolset()

    @toolset.tool
    async def get_task_summary(ctx: RunContext[AuditDeps]) -> dict:
        """任务标准化流水总览（只返聚合数，不返明细）。

        含 standard / unparsed 计数、金额合计、时间跨度。摸底用此工具，下钻用带
        参数工具。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        rows = await _load_standard_rows(db, task_id)
        amounts = [parse_amount(r.amount) for r in rows if r.amount]
        total_amount = sum(amounts)
        times = [parse_datetime(r.transaction_time) for r in rows if r.transaction_time]
        valid_times = [t for t in times if t]
        unparsed_count = (
            await db.execute(
                select(func.count(FlowRecordRow.id)).where(
                    FlowRecordRow.task_id == task_id,
                    FlowRecordRow.record_type == "unparsed",
                )
            )
        ).scalar() or 0
        return {
            "standard_count": len(rows),
            "unparsed_count": int(unparsed_count),
            "total_amount": f"¥{total_amount:,.2f}",
            "time_span": {
                "start": valid_times[0].strftime("%Y-%m-%d %H:%M:%S") if valid_times else "",
                "end": valid_times[-1].strftime("%Y-%m-%d %H:%M:%S") if valid_times else "",
            }
            if valid_times
            else {"start": "", "end": ""},
        }

    @toolset.tool
    async def query_by_time(
        ctx: RunContext[AuditDeps],
        *,
        start: str | None = None,
        end: str | None = None,
        hours: list[int] | None = None,
        limit: int = _DEFAULT_DETAIL_LIMIT,
    ) -> list[dict]:
        """按交易时间窗口查 standard 流水。

        **默认剔除时分秒==00:00:00 的「只记日期」噪音（不可关）**——全 0 是噪音。
        二选一传参：``start``+``end``（ISO YYYY-MM-DD，含）区间，或 ``hours``
        （交易小时列表，如夜间 ``[22,23,0,1,2,3,4,5]``）。

        Args:
            start: ISO YYYY-MM-DD，区间起（含）。可空。
            end: ISO YYYY-MM-DD，区间止（含）。可空。
            hours: 交易小时列表（0-23），命中其一即返回。可空。
            limit: 返回条数上限，默认 200，硬上限 1000。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        n = _clamp_limit(limit)
        rows = await _load_standard_rows(db, task_id)

        start_dt = parse_datetime(start) if start else None
        end_dt = parse_datetime(end) if end else None
        # end 含当日 → 加一天做上界。
        if end_dt:
            end_dt = end_dt + timedelta(days=1)
        hours_set = set(hours) if hours else None

        out: list[dict] = []
        for r in rows:
            if not _has_hms(r.transaction_time):
                continue
            dt = parse_datetime(r.transaction_time)
            if dt is None:
                continue
            if start_dt and dt < start_dt:
                continue
            if end_dt and dt >= end_dt:
                continue
            if hours_set is not None and dt.hour not in hours_set:
                continue
            out.append(_row_to_dict(r))
            if len(out) >= n:
                break
        return out

    @toolset.tool
    async def query_by_amount(
        ctx: RunContext[AuditDeps],
        *,
        min: float | None = None,
        max: float | None = None,
        mode: str | None = None,
        limit: int = _DEFAULT_DETAIL_LIMIT,
    ) -> list[dict]:
        """按金额区间查 standard 流水。

        ``min``/``max`` 直接传区间，或 ``mode`` 让 agent 不用算阈值：
        * ``large`` —— 大额（≥``min``，``min`` 缺省取 50000）。
        * ``round`` —— 异常整数金额（尾随 ≥4 个 0）。
        * ``evasion`` —— 阈值下浮 band 内（<``min`` 且 ≥``min``*0.8，规避大额上报）。

        Args:
            min: 金额下限（含），可空。
            max: 金额上限（含），可空。
            mode: large / round / evasion，可空。
            limit: 返回条数上限，默认 200，硬上限 1000。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        n = _clamp_limit(limit)
        rows = await _load_standard_rows(db, task_id)

        lo = float(min) if min is not None else None
        hi = float(max) if max is not None else None
        mode_str = (mode or "").strip().lower() or None
        if mode_str == "large" and lo is None:
            lo = 50000.0

        out: list[dict] = []
        for r in rows:
            amt = parse_amount(r.amount)
            if amt <= 0:
                continue
            if mode_str == "round":
                # 尾随 ≥4 个 0：整数且 %10000==0。
                if amt < 10000 or abs(amt - round(amt)) > 1e-6:
                    continue
                if int(round(amt)) % 10000 != 0:
                    continue
            elif mode_str == "evasion":
                band_lo = (lo or 50000.0) * 0.8
                band_hi = lo or 50000.0
                if not (band_lo <= amt < band_hi):
                    continue
            else:
                if lo is not None and amt < lo:
                    continue
                if hi is not None and amt > hi:
                    continue
            out.append(_row_to_dict(r))
            if len(out) >= n:
                break
        return out

    @toolset.tool
    async def query_by_counterparty(
        ctx: RunContext[AuditDeps],
        *,
        name: str | None = None,
        min_count: int | None = None,
        limit: int = _DEFAULT_DETAIL_LIMIT,
    ) -> list[dict]:
        """按对手方查 standard 流水。

        传 ``name`` 查指定对手方；传 ``min_count`` 一步出「≥N 笔的对手方」
        （返按笔数降序的对手方聚合，每项含 counterparty_name / count / total_amount /
        sample_record_ids）。两者同传时 ``min_count`` 优先（聚合模式）。

        Args:
            name: 对手方名称（精确匹配 counterparty_name），可空。
            min_count: 只返交易笔数 ≥ 此值的对手方（聚合模式），可空。
            limit: 返回条数上限（明细模式默认 200；聚合模式默认 50），硬上限 1000。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        rows = await _load_standard_rows(db, task_id)

        if min_count is not None:
            # 聚合模式：按对手方聚合，过滤 ≥min_count，按笔数降序。
            agg: dict[str, dict] = {}
            for r in rows:
                cp = (r.counterparty_name or "").strip()
                if not cp:
                    continue
                entry = agg.setdefault(
                    cp, {"count": 0, "total_amount": 0.0, "sample_record_ids": []}
                )
                entry["count"] += 1
                entry["total_amount"] += parse_amount(r.amount)
                if len(entry["sample_record_ids"]) < 10:
                    entry["sample_record_ids"].append(r.id)
            items = [
                {
                    "counterparty_name": cp,
                    "count": e["count"],
                    "total_amount": f"¥{e['total_amount']:,.2f}",
                    "sample_record_ids": e["sample_record_ids"],
                }
                for cp, e in agg.items()
                if e["count"] >= int(min_count)
            ]
            items.sort(key=lambda x: x["count"], reverse=True)
            agg_limit = min(_clamp_limit(limit), 50) if limit != _DEFAULT_DETAIL_LIMIT else 50
            return items[:agg_limit]

        # 明细模式：按 name 精确匹配。
        n = _clamp_limit(limit)
        target = (name or "").strip()
        out: list[dict] = []
        for r in rows:
            if target and (r.counterparty_name or "").strip() != target:
                continue
            out.append(_row_to_dict(r))
            if len(out) >= n:
                break
        return out

    @toolset.tool
    async def query_burst(
        ctx: RunContext[AuditDeps],
        *,
        window_minutes: int,
        min_count: int = 2,
        limit: int = 50,
    ) -> list[dict]:
        """短间隔簇 / 快进快出（同对手方短时密集交易）。

        时间聚类逻辑封进工具（不让 agent 拼）：按对手方分组，组内按时间排序，
        相邻交易间隔 ≤``window_minutes`` 分钟归同一簇；簇内笔数 ≥``min_count``
        即上报。返按簇内笔数降序的簇列表，每项含 counterparty_name / count /
        time_window / total_amount / record_ids。

        Args:
            window_minutes: 簇间隔阈值（分钟），相邻交易间隔 ≤此值归同簇。
            min_count: 簇内最少笔数才上报，默认 2。
            limit: 返回簇数上限，默认 50，硬上限 1000。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        n = _clamp_limit(limit)
        rows = await _load_standard_rows(db, task_id)

        grouped: dict[str, list[tuple[Any, FlowRecordRow]]] = {}
        for r in rows:
            if not _has_hms(r.transaction_time):
                continue
            dt = parse_datetime(r.transaction_time)
            if dt is None:
                continue
            cp = (r.counterparty_name or "").strip()
            if not cp:
                continue
            grouped.setdefault(cp, []).append((dt, r))

        cases: list[dict] = []
        threshold = timedelta(minutes=int(window_minutes))
        for cp, items in grouped.items():
            items.sort(key=lambda x: x[0])
            cluster: list[tuple[Any, FlowRecordRow]] = []
            for dt, r in items:
                if not cluster:
                    cluster = [(dt, r)]
                    continue
                if dt - cluster[-1][0] <= threshold:
                    cluster.append((dt, r))
                else:
                    if len(cluster) >= int(min_count):
                        cases.append(_build_burst_case(cp, cluster))
                    cluster = [(dt, r)]
            if len(cluster) >= int(min_count):
                cases.append(_build_burst_case(cp, cluster))

        cases.sort(key=lambda c: c["count"], reverse=True)
        return cases[:n]

    return toolset


def _build_burst_case(
    counterparty: str, cluster: list[tuple[Any, FlowRecordRow]]
) -> dict:
    """单个短间隔簇 → dict（query_burst 用）。"""
    total = sum(parse_amount(r.amount) for _, r in cluster)
    return {
        "counterparty_name": counterparty,
        "count": len(cluster),
        "time_window": (
            f"{cluster[0][0].strftime('%Y-%m-%d %H:%M:%S')} "
            f"至 {cluster[-1][0].strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        "total_amount": f"¥{total:,.2f}",
        "record_ids": [r.id for _, r in cluster[:20]],
    }


# ---------------------------------------------------------------------------
# 维度 agent —— 跑分析（动态 instructions=该维度 prompt）
# ---------------------------------------------------------------------------


def get_dimension_agent(
    dimension_prompt: str, *, model: Optional[LLMModel] = None
) -> Agent:
    """建/取维度 agent（模块级单例，缓存 key 含 instructions → 每维度各自单例）。

    挂 ``ReadAuditToolset``（5 个只读工具，经 ``toolsets=`` 注入）。``output_type=
    DimensionFindingResult``。``instructions=dimension_prompt``（动态，跑分析时
    注入该维度的拼好 prompt）。
    """
    params = _resolve_agent_params(model, fallback_max_tokens=_MAX_TOKENS_DIMENSION)
    agent = get_agent(
        DimensionFindingResult,
        dimension_prompt,
        base_url=params["base_url"],
        api_key=params["api_key"],
        model=params["model"],
        timeout=params["timeout"],
        max_tokens=params["max_tokens"],
        thinking=params["thinking"],
        temperature=params["temperature"],
        deps_type=AuditDeps,
        toolsets=[_readonly_toolset()],
    )
    return agent


# 模块级共享只读 Toolset 单例（两 agent 共用同一实例，避免每次重建）。
_READONLY_TOOLSET: Optional[FunctionToolset[AuditDeps]] = None


def _readonly_toolset() -> FunctionToolset[AuditDeps]:
    """模块级单例只读 Toolset（懒构造，两 agent 共享同一实例）。"""
    global _READONLY_TOOLSET
    if _READONLY_TOOLSET is None:
        _READONLY_TOOLSET = build_read_audit_toolset()
    return _READONLY_TOOLSET


async def run_dimension(
    deps: AuditDeps,
    dimension: AuditDimension,
    *,
    model: Optional[LLMModel] = None,
) -> DimensionFindingResult:
    """跑单个维度：该维度 prompt 注入维度 agent.instructions → agent.run。

    agentic 单次 run 内多步工具循环（agent 自己调 N 次工具直到满意）。零命中 →
    ``findings`` 为空。LLM 不可用 / 失败 → 抛异常由 service 层 try/except 跳过
    该维度（容错 spec）。
    """
    agent = get_dimension_agent(dimension.prompt, model=model)
    user_prompt = (
        f"请按上述维度「{dimension.name}」对本任务 standard 流水跑分析，"
        f"按需调用只读工具，产出 DimensionFindingResult。"
    )
    result = await agent.run(user_prompt, deps=deps)
    return result.output


# ---------------------------------------------------------------------------
# 追问 agent —— 多轮对话 + query_findings + create_dimension
# ---------------------------------------------------------------------------


def get_qa_agent(*, model: Optional[LLMModel] = None) -> Agent:
    """建/取追问 agent（模块级单例，静态 instructions）。

    挂 ``ReadAuditToolset``（经 ``toolsets=``）+ ``query_findings`` + ``create_dimension``
    （经 ``@agent.tool``，进 ``_function_toolset``）。运行时两者合并。``output_type=str``，
    阶段卡 STAGE_AI_QA。
    """
    params = _resolve_agent_params(model, fallback_max_tokens=_MAX_TOKENS_QA)
    agent = get_agent(
        str,
        _QA_INSTRUCTIONS,
        base_url=params["base_url"],
        api_key=params["api_key"],
        model=params["model"],
        timeout=params["timeout"],
        max_tokens=params["max_tokens"],
        thinking=params["thinking"],
        temperature=params["temperature"],
        deps_type=AuditDeps,
        toolsets=[_readonly_toolset()],
    )
    # query_findings + create_dimension 经 @agent.tool 进 _function_toolset。
    # sentinel 避免缓存命中后重复注册（tool name 冲突）。
    tag = "_qa_extra_tools_registered"
    if not getattr(agent, tag, False):
        _register_qa_extra_tools(agent)
        setattr(agent, tag, True)
    return agent


def _register_qa_extra_tools(agent: Agent) -> None:
    """在追问 agent 上注册 query_findings + create_dimension（只读 + 沉淀）。

    ``create_dimension`` 限 ``steps.tool`` 白名单（5 个只读 + query_findings），
    编造 → ``ModelRetry``；服务端拼 prompt 落 ``AuditDimension``（source=agent,
    enabled=false, created_by=当前用户）。**agent 无删除工具**。
    """

    @agent.tool
    async def query_findings(ctx: RunContext[AuditDeps]) -> list[dict]:
        """查本任务已有的所有异常发现（findings），只读。

        返每条 finding 的 type / severity / counterparty / amount / detail_text /
        confidence / status / dimension_name。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        result = await db.execute(
            select(Finding)
            .where(Finding.task_id == task_id)
            .order_by(Finding.id.asc())
        )
        rows = result.scalars().all()
        out: list[dict] = []
        for f in rows:
            dim_name = None
            if f.dimension_id is not None:
                dim_row = (
                    await db.execute(
                        select(AuditDimension.name).where(
                            AuditDimension.id == f.dimension_id
                        )
                    )
                ).scalar_one_or_none()
                dim_name = dim_row
            out.append(
                {
                    "id": f.id,
                    "type": f.type,
                    "severity": f.severity,
                    "counterparty": f.counterparty,
                    "amount": f.amount,
                    "detail_text": f.detail_text,
                    "confidence": f.confidence,
                    "status": f.status,
                    "dimension_name": dim_name,
                }
            )
        return out

    @agent.tool
    async def create_dimension(
        ctx: RunContext[AuditDeps],
        *,
        name: str,
        purpose: str,
        steps: list[dict],
        judgment: str,
        severity: str,
    ) -> str:
        """沉淀新审查维度（草稿，需人在维度管理页启用才进 analyze）。

        字段缺一拒绝。``steps.tool`` 限只读工具白名单（5 个只读 + query_findings），
        编造 → ModelRetry。服务端用固定模板拼 ``prompt`` 写库（source=agent,
        enabled=false, created_by=当前用户）。

        Args:
            name: 维度名（≤20 字）。
            purpose: 要查什么异常（1-2 句）。
            steps: 按序列出要调哪些工具、传什么参数（``list[{tool, params}]``，
                tool 限白名单）。
            judgment: 命中 / severity 判定标准。
            severity: high | medium | low。
        """
        db = ctx.deps.db
        user_id = ctx.deps.user_id

        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > 20:
            raise ModelRetry("维度名不能为空且需 ≤20 字")
        clean_purpose = (purpose or "").strip()
        if not clean_purpose:
            raise ModelRetry("purpose 不能为空（1-2 句描述要查什么异常）")
        clean_judgment = (judgment or "").strip()
        if not clean_judgment:
            raise ModelRetry("judgment 不能为空（命中/severity 判定标准）")
        sev = (severity or "").strip().lower()
        if sev not in DIMENSION_SEVERITIES:
            raise ModelRetry(
                f"severity 必须是 {DIMENSION_SEVERITIES} 之一，收到：{severity}"
            )

        # 校验 steps：list[{tool, params}]，tool 限白名单。
        if not isinstance(steps, list) or not steps:
            raise ModelRetry("steps 必须是非空 list[{tool, params}]")
        clean_steps: list[dict] = []
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ModelRetry(f"steps[{idx}] 必须是 dict {{tool, params}}")
            tool = str(step.get("tool") or "").strip()
            if tool not in READONLY_TOOL_WHITELIST:
                raise ModelRetry(
                    f"steps[{idx}].tool '{tool}' 不在白名单 "
                    f"({sorted(READONLY_TOOL_WHITELIST)})，不要编造工具名"
                )
            params = step.get("params") or {}
            if not isinstance(params, dict):
                raise ModelRetry(f"steps[{idx}].params 必须是 dict")
            clean_steps.append({"tool": tool, "params": params})

        prompt = build_dimension_prompt(
            name=clean_name,
            purpose=clean_purpose,
            steps=clean_steps,
            judgment=clean_judgment,
            severity=sev,
        )
        dim = AuditDimension(
            name=clean_name,
            source=SOURCE_AGENT,
            purpose=clean_purpose,
            steps=clean_steps,
            judgment=clean_judgment,
            severity=sev,
            prompt=prompt,
            enabled=False,
            created_by=user_id,
        )
        db.add(dim)
        await db.flush()
        logger.info(
            "create_dimension 沉淀草稿维度: id=%s name=%s created_by=%s",
            dim.id,
            clean_name,
            user_id,
        )
        # 返结构化信息（PRD §六）：chat() 从工具返回里提取 name + severity
        # 填 sedimented_dimension，前端气泡渲染「已沉淀维度：XXX（草稿，待启用）」。
        return {
            "id": dim.id,
            "name": clean_name,
            "severity": sev,
            "enabled": False,
            "message": (
                f"已沉淀维度「{clean_name}」（草稿，enabled=false，"
                f"需人在维度管理页启用后才进入 analyze）"
            ),
        }


# ---------------------------------------------------------------------------
# chat —— 多轮对话（message_history + ModelMessagesTypeAdapter 往返）
# ---------------------------------------------------------------------------


class ToolTrace(BaseModel):
    """单次工具调用痕迹（前端气泡小字「🔍 已查询：…」用）."""

    tool: str
    summary: str


class SedimentedDimension(BaseModel):
    """本轮流问沉淀出的草稿维度信息（前端气泡「已沉淀维度：XXX（草稿，待启用）」）."""

    name: str
    severity: str


class ChatResult(BaseModel):
    """chat() 结构化返回（替代旧 tuple，PRD §十/§六）."""

    reply: str
    tool_traces: list[ToolTrace] = []
    sedimented_dimension: Optional[SedimentedDimension] = None
    new_history_json: str  # 序列化新 history（service 存回 AuditConversation）


def _summarize_tool_return(tool_name: str, content: Any) -> str:
    """按工具类型给一句可读 summary（PRD §十：如 query_by_time → 「夜间交易：37条」）."""
    if isinstance(content, list):
        n = len(content)
        if n and isinstance(content[0], dict):
            cp = content[0].get("counterparty_name")
            if cp:
                return f"命中 {n} 条，样本对手：{cp}"
        return f"返回 {n} 条"
    if isinstance(content, dict):
        if "standard_count" in content:
            return f"standard {content.get('standard_count')} 条 / 金额 {content.get('total_amount')}"
        if "counterparty_name" in content and "count" in content:
            return f"对手 {content.get('counterparty_name')}：{content.get('count')} 笔"
        if "message" in content:
            return str(content.get("message"))
    return str(content)[:80]


def _extract_tool_traces(messages: list) -> list[ToolTrace]:
    """从 result.all_messages() 提取本轮 agent 调过的工具 + 每次调用的简短摘要.

    遍历 ModelResponse.parts 取 ToolCallPart（工具名 + 参数），匹配后续
    ModelRequest.parts 的 ToolReturnPart（同 tool_call_id）拿返回值，按工具
    类型给可读 summary。pydantic-ai 消息格式 model-independent（conventions.md）。
    """
    # 先建 tool_call_id -> return content 映射。
    returns_by_id: dict[str, Any] = {}
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in getattr(msg, "parts", []) or []:
                if isinstance(part, ToolReturnPart):
                    returns_by_id[part.tool_call_id] = part.content

    traces: list[ToolTrace] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in getattr(msg, "parts", []) or []:
                if isinstance(part, ToolCallPart):
                    content = returns_by_id.get(part.tool_call_id)
                    traces.append(
                        ToolTrace(
                            tool=part.tool_name,
                            summary=_summarize_tool_return(part.tool_name, content),
                        )
                    )
    return traces


def _extract_sedimented_dimension(messages: list) -> Optional[SedimentedDimension]:
    """本轮若调了 create_dimension，从其工具返回里取 name + severity."""
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in getattr(msg, "parts", []) or []:
                if isinstance(part, ToolReturnPart) and part.tool_name == "create_dimension":
                    content = part.content
                    if isinstance(content, dict):
                        name = content.get("name")
                        sev = content.get("severity")
                        if name and sev:
                            return SedimentedDimension(name=str(name), severity=str(sev))
    return None


def extract_history_messages(message_history_json: str | None) -> list[dict[str, str]]:
    """从序列化的 message_history 抽取可读的 user/ai 消息（GET 会话历史用）.

    message_history 是 pydantic-ai ModelMessages（ModelRequest/ModelResponse）。遍历：
    ``ModelRequest`` 的 ``UserPromptPart`` → user 消息；``ModelResponse`` 的 ``TextPart``
    → ai 消息（同一 response 内多条 TextPart 合并）。``ToolCallPart``/``ToolReturnPart``
    不展示成气泡——历史只回放文本对话（工具痕迹仅当前轮 live 显）.
    """
    history = ModelMessagesTypeAdapter.validate_json(message_history_json or "[]")
    out: list[dict[str, str]] = []
    for msg in history:
        if isinstance(msg, ModelRequest):
            for part in getattr(msg, "parts", []) or []:
                if isinstance(part, UserPromptPart):
                    content = part.content
                    text = content if isinstance(content, str) else str(content)
                    if text.strip():
                        out.append({"role": "user", "text": text})
        elif isinstance(msg, ModelResponse):
            texts: list[str] = []
            for part in getattr(msg, "parts", []) or []:
                if isinstance(part, TextPart) and part.content:
                    texts.append(part.content)
            if texts:
                out.append({"role": "ai", "text": "\n".join(texts)})
    return out


async def chat(
    deps: AuditDeps,
    message_history_json: str | None,
    user_msg: str,
    *,
    model: Optional[LLMModel] = None,
) -> ChatResult:
    """多轮追问：反序列化 history → agent.run(msg, message_history=history) →
    序列化新 history 存回 + 提取工具调用痕迹 + 沉淀维度标记。

    Args:
        deps: per-request deps（db + task_id + user_id）。
        message_history_json: 上一轮序列化的 message_history（JSON 字符串），
            为空或 "[]" 表示首轮。
        user_msg: 本轮用户提问。
        model: ai_qa 阶段指派的卡片（None → 回退 env settings）。

    Returns:
        ChatResult：reply（agent 回复）+ tool_traces（本轮流问调过的只读工具
        痕迹，前端气泡小字「🔍 已查询：…」）+ sedimented_dimension（本轮若调
        create_dimension 沉淀出的草稿维度 name/severity，前端气泡「已沉淀维度：
        XXX（草稿，待启用）」）+ new_history_json（存回 AuditConversation）。
    """
    agent = get_qa_agent(model=model)
    history = ModelMessagesTypeAdapter.validate_json(message_history_json or "[]")
    result = await agent.run(user_msg, deps=deps, message_history=history)
    all_messages = result.all_messages()
    return ChatResult(
        reply=str(result.output),
        tool_traces=_extract_tool_traces(all_messages),
        sedimented_dimension=_extract_sedimented_dimension(all_messages),
        new_history_json=to_json(all_messages).decode(),
    )
