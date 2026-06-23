# -*- coding: utf-8 -*-
"""S7 章节化审查报告 — 确定性模板拼装.

不接真实 LLM（占位 + 确定性模板）。聚合 S5 ``flow_records``（standard 记录
数、渠道分布、cleaning_committed 时间）+ S6 ``findings``（总数、severity
分组、status 分组）+ ``Task`` 基础信息，按 6 章模板拼装 Markdown content。

6 章固定顺序 + 固定标题（order_index 0-5）：
  0 概述 / 1 被审查对象 / 2 数据范围 / 3 异常发现汇总 / 4 风险评估 / 5 结论建议

TODO 用户后续接真实 agent.run 后，单章重生成可改为 agent 输出（deps_type 传
类型 / deps 传实例 / message_history / ModelMessagesTypeAdapter）。本轮保持
占位确定性，保证可测可重放。

单色原则：severity 用灰阶递进描述（高/中/低），禁红黄绿；风险等级灰阶表述。
不删减精神：content 是可再生的派生数据，重生成重写 content 不改原始记录
（S5 flow_records.raw_payload 已兜底）。
"""

from collections import Counter
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Finding, FlowRecordRow, Task
from app.models.llm_model import LLMModel
from app.models.llm_model_assignment import STAGE_REPORT_GENERATION
from app.services.llm_model_service import get_stage_model


# 6 章固定标题（order_index 0-5）。
CHAPTER_TITLES: list[str] = [
    "概述",
    "被审查对象",
    "数据范围",
    "异常发现汇总",
    "风险评估",
    "结论建议",
]


def chapter_titles() -> list[str]:
    """6 章固定标题（供测试与路由引用，避免硬编码漂移）."""
    return list(CHAPTER_TITLES)


# ---------------------------------------------------------------------------
# 阶段模型卡片预留接线（06-23-llm-model-card）
# ---------------------------------------------------------------------------
# report_generation 阶段当前是占位（确定性模板拼装，不调真实 LLM）。本切片只
# 确保它**能**按阶段读卡片（预留接线函数），等后续任务接真实 agent.run 时生效。


async def get_report_generation_model(db: AsyncSession) -> Optional[LLMModel]:
    """report_generation 阶段指派的卡片（预留接线，占位阶段当前不调真实 LLM）。

    Returns:
        指派的 ``LLMModel`` 或 None（未指派 → 后续接真实 LLM 时回退兜底）。
    """
    return await get_stage_model(db, STAGE_REPORT_GENERATION)


def _fmt_datetime(value: datetime | None) -> str:
    """DateTime → 'YYYY-MM-DD HH:MM' 本地时间字符串，None → '—'."""
    if value is None:
        return "—"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _fmt_period(start: datetime | None, end: datetime | None) -> str:
    """审查期间：start ~ end，空值用 '—'."""
    s = _fmt_datetime(start) if start else "—"
    e = _fmt_datetime(end) if end else "—"
    if start is None and end is None:
        return "—"
    return f"{s} ~ {e}"


# ---------------------------------------------------------------------------
# 数据聚合
# ---------------------------------------------------------------------------


async def _aggregate(
    db: AsyncSession, task: Task
) -> dict:
    """聚合 S5 flow_records + S6 findings 统计，供 6 章模板共用."""
    # S5 flow_records 统计：standard 记录数 + 渠道分布。
    std_count = (
        await db.execute(
            select(func.count(FlowRecordRow.id)).where(
                FlowRecordRow.task_id == task.id,
                FlowRecordRow.record_type == "standard",
            )
        )
    ).scalar() or 0

    channel_rows = (
        await db.execute(
            select(FlowRecordRow.channel, func.count(FlowRecordRow.id))
            .where(
                FlowRecordRow.task_id == task.id,
                FlowRecordRow.record_type == "standard",
            )
            .group_by(FlowRecordRow.channel)
        )
    ).all()
    channel_dist = {row[0] or "未标注": row[1] for row in channel_rows}

    # 文档数（不同 document_id 数；null 不计）。
    doc_count = (
        await db.execute(
            select(func.count(FlowRecordRow.document_id.distinct())).where(
                FlowRecordRow.task_id == task.id,
                FlowRecordRow.document_id.is_not(None),
            )
        )
    ).scalar() or 0

    # S6 findings：总数 + severity 分组 + status 分组。
    findings_rows = (
        await db.execute(
            select(Finding).where(Finding.task_id == task.id)
        )
    ).scalars().all()
    severity_counts = Counter(f.severity for f in findings_rows)
    status_counts = Counter(f.status for f in findings_rows)
    high_findings = [f for f in findings_rows if f.severity == "high"]

    # cleaning_committed 时间来自 Task.config（S5 清洗提交锁）。
    config = dict(task.config or {}) if task.config else {}
    cleaning_committed = config.get("cleaning_committed")

    return {
        "std_count": std_count,
        "channel_dist": channel_dist,
        "doc_count": doc_count,
        "findings_total": len(findings_rows),
        "severity_counts": severity_counts,
        "status_counts": status_counts,
        "high_findings": high_findings,
        "cleaning_committed": cleaning_committed,
    }


# ---------------------------------------------------------------------------
# 6 章模板（确定性拼装 Markdown）
# ---------------------------------------------------------------------------


def _build_overview(task: Task) -> str:
    """第 0 章 概述：任务标题/编号/状态/创建时间/审查期间."""
    period = _fmt_period(task.audit_start, task.audit_end)
    lines = [
        f"## 概述",
        "",
        f"- 任务标题：{task.title}",
        f"- 任务编号：{task.id}",
        f"- 任务状态：{task.status}",
        f"- 创建时间：{_fmt_datetime(task.created_at)}",
        f"- 审查期间：{period}",
        "",
        "本报告由智行卫士审查系统基于标准化流水与 AI 分析结论自动生成，",
        "供审计专员复核与定稿。",
    ]
    return "\n".join(lines) + "\n"


def _build_subject(task: Task) -> str:
    """第 1 章 被审查对象：员工工号/姓名/部门（来自 Task 字段）."""
    lines = [
        f"## 被审查对象",
        "",
        f"- 员工姓名：{task.employee_name or '—'}",
        f"- 员工工号：{task.employee_id or '—'}",
        f"- 所属部门：{task.department or '—'}",
        "",
        f"审查期间：{_fmt_period(task.audit_start, task.audit_end)}",
    ]
    return "\n".join(lines) + "\n"


def _build_data_scope(task: Task, agg: dict) -> str:
    """第 2 章 数据范围：文档数/standard 记录数/渠道分布/清洗提交时间."""
    channel_lines = (
        [f"  - {ch}：{cnt} 条" for ch, cnt in agg["channel_dist"].items()]
        if agg["channel_dist"]
        else ["  - 暂无渠道分布数据"]
    )
    committed = agg["cleaning_committed"]
    committed_text = committed if committed else "未提交"
    lines = [
        f"## 数据范围",
        "",
        f"- 文档数：{agg['doc_count']}",
        f"- 标准化记录数：{agg['std_count']}",
        f"- 渠道分布：",
        *channel_lines,
        f"- 清洗提交时间：{committed_text}",
        "",
        "数据范围以 S5 清洗标准化提交锁定的 standard 快照为准；",
        "未解析行与排除行保留在 flow_records 中，不参与本报告统计。",
    ]
    return "\n".join(lines) + "\n"


def _build_findings_summary(task: Task, agg: dict) -> str:
    """第 3 章 异常发现汇总：总数 + severity 分组 + status 分组（灰阶递进）."""
    sev = agg["severity_counts"]
    st = agg["status_counts"]
    # 灰阶递进描述（高=最深 / 中=中 / 低=浅），禁红黄绿。
    lines = [
        f"## 异常发现汇总",
        "",
        f"- 异常发现总数：{agg['findings_total']}",
        f"- 按风险等级分组（灰阶递进，高 > 中 > 低）：",
        f"  - 高风险：{sev.get('high', 0)} 项",
        f"  - 中风险：{sev.get('medium', 0)} 项",
        f"  - 低风险：{sev.get('low', 0)} 项",
        f"- 按复核状态分组：",
        f"  - 待处理：{st.get('pending', 0)} 项",
        f"  - 已采纳：{st.get('accepted', 0)} 项",
        f"  - 已忽略：{st.get('ignored', 0)} 项",
        "",
        "风险等级采用灰阶表述，不使用红黄绿等彩色标识。",
    ]
    return "\n".join(lines) + "\n"


def _build_risk_assessment(task: Task, agg: dict) -> str:
    """第 4 章 风险评估：high severity findings 列表 + 风险等级灰阶表述.

    异常条目卡片块：对 high severity findings 发出
    ``> finding: **{type}** | 金额 {amount} | 对手 {counterparty} | {description}``
    行，前端 ``FindingCard`` 渲染为单色卡片块（标题/金额/对手/描述 +
    "详见关联记录"入口占位）。单色原则，禁红黄绿。
    """
    high = agg["high_findings"]
    # 风险等级灰阶表述（占位确定性）。
    if high:
        level_text = "整体风险等级：偏高（存在高风险异常发现，建议重点关注）。"
    elif agg["findings_total"] > 0:
        level_text = "整体风险等级：中等（存在中低风险异常发现，建议常规复核）。"
    else:
        level_text = "整体风险等级：较低（未发现异常，建议常规复核）。"

    lines = [f"## 风险评估", "", level_text, ""]
    if high:
        lines.append("高风险异常发现明细：")
        lines.append("")
        for f in high:
            amount = f.amount or "—"
            counterparty = f.counterparty or "—"
            lines.append(
                f"> finding: **{f.type}** | 金额 {amount} | 对手 {counterparty} | {f.description}"
            )
        lines.append("")
        lines.append("（关联记录入口占位：真实 agent 工具产出后展示 flow_record id。）")
    else:
        lines.append("暂无高风险异常发现。")
    return "\n".join(lines) + "\n"


def _build_conclusion(task: Task, agg: dict) -> str:
    """第 5 章 结论建议：模板化建议（有 high finding → 重点关注；无 → 常规复核）."""
    high = agg["high_findings"]
    if high:
        advice = (
            "- 建议对高风险异常发现进行重点复核，结合原始凭证核实交易背景与金额合理性。"
        )
    else:
        advice = "- 建议进行常规复核，确认数据范围与异常发现汇总无遗漏。"
    lines = [
        f"## 结论建议",
        "",
        advice,
        "",
        "本结论由确定性模板生成（占位骨架），用户后续可接入真实 LLM 推理。",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------


async def build_all_chapters(db: AsyncSession, task: Task) -> list[str]:
    """聚合数据并拼装 6 章 Markdown content，按固定 order_index 顺序返回."""
    agg = await _aggregate(db, task)
    return [
        _build_overview(task),
        _build_subject(task),
        _build_data_scope(task, agg),
        _build_findings_summary(task, agg),
        _build_risk_assessment(task, agg),
        _build_conclusion(task, agg),
    ]


async def build_one_chapter(
    db: AsyncSession, task: Task, order_index: int
) -> str:
    """单章重生成：只重拼指定 order_index 的章节 content（占位确定性）.

    TODO 用户后续接真实 agent.run：把此处替换为
    ``agent.run(user_prompt, deps=AuditDeps(db=db, task_id=task.id),
    message_history=ModelMessagesTypeAdapter.validate_json(history))``，
    output_type 用 pydantic 模型约束单章 content。
    """
    chapters = await build_all_chapters(db, task)
    if 0 <= order_index < len(chapters):
        return chapters[order_index]
    return ""
