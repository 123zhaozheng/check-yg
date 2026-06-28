# -*- coding: utf-8 -*-
"""S7 章节化审查报告 — LLM agent 生成（06-28 Phase 2）+ 确定性模板兜底.

聚合 S5 ``flow_records``（standard 记录数、渠道分布、cleaning_committed 时间）+
S6 ``findings``（**已采纳 accepted** 总数、severity 分组、status 分组）+
**关键词审查 KeywordHit（confirmed）** + **完整性校验（balance_check findings）**
+ ``Task`` 基础信息。

**Phase 2（06-28-report-fusion-word-cover）**：每章调 ``run_chapter`` 产 LLM
markdown 正文（pydantic-ai agent，围绕真实聚合数据写，禁编造数字）。LLM 不可用
/失败 → 该章回退确定性模板 ``_build_*``（兜底，不崩）。

8 章固定顺序 + 固定标题（order_index 0-7）：
  0 概述 / 1 被审查对象 / 2 数据范围 / 3 完整性校验（余额） / 4 关键词审查 /
  5 异常发现汇总 / 6 风险评估 / 7 结论建议

报告融合上游硬底线（06-28-report-fusion-word-cover）：
  * findings 只取 **accepted**（pending/ignored 不计）。
  * 关键词审查章只取 **confirmed** 命中（与 findings 的 accepted 对齐）。
  * 完整性校验章取 **accepted** 的 ``source=balance_check`` finding。
  * 追问(AuditConversation) **不进报告**（实时辅助工具，非结论）。

单色原则：severity 用灰阶递进描述（高/中/低），禁红黄绿；风险等级灰阶表述。
不删减精神：content 是可再生的派生数据，重生成重写 content 不改原始记录
（S5 flow_records.raw_payload 已兜底）。
"""

import json
import logging
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.report_agent import ReportDeps, run_chapter
from app.models import (
    Finding,
    FlowRecordRow,
    KeywordCard,
    KeywordHit,
    KeywordTerm,
    Task,
)
from app.models.llm_model import LLMModel

logger = logging.getLogger(__name__)


# 8 章固定标题（order_index 0-7）。
CHAPTER_TITLES: list[str] = [
    "概述",
    "被审查对象",
    "数据范围",
    "完整性校验（余额）",
    "关键词审查",
    "异常发现汇总",
    "风险评估",
    "结论建议",
]


def chapter_titles() -> list[str]:
    """8 章固定标题（供测试与路由引用，避免硬编码漂移）."""
    return list(CHAPTER_TITLES)


def _fmt_datetime(value: datetime | None) -> str:
    """DateTime → 'YYYY-MM-DD HH:MM' 本地时间字符串，None → '—'."""
    if value is None:
        return "—"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _fmt_date(value: datetime | None) -> str:
    """DateTime → 'YYYY-MM-DD' 本地时间字符串，None → '—'."""
    if value is None:
        return "—"
    try:
        return value.strftime("%Y-%m-%d")
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
    """聚合 S5 flow_records + S6 findings（accepted）+ 关键词审查（confirmed）+
    余额校验（accepted）统计，供 8 章模板共用。

    findings 硬底线：只计 ``status == 'accepted'``（pending/ignored 不进报告）。
    关键词审查：只计 ``status == 'confirmed'``（与 findings accepted 对齐）。
    """
    # S5 flow_records 统计：standard 记录数 + 渠道分布。
    from sqlalchemy import func

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

    # S6 findings：只取 accepted（硬底线：pending/ignored 不进报告）。
    findings_rows = (
        await db.execute(
            select(Finding).where(
                Finding.task_id == task.id,
                Finding.status == "accepted",
            )
        )
    ).scalars().all()
    severity_counts = Counter(f.severity for f in findings_rows)
    # status_counts 基于 accepted 集（已采纳 = findings_total；其余态为 0，
    # 因为非 accepted 已被过滤）。
    status_counts = Counter(f.status for f in findings_rows)
    high_findings = [f for f in findings_rows if f.severity == "high"]

    # 余额校验 finding（accepted 的 source=balance_check）。
    balance_findings = [
        f for f in findings_rows if f.source == "balance_check"
    ]

    # 关键词审查（confirmed）聚合：join card/term 取关键词名 + 关联
    # flow_record 取金额（一次 join，防 N+1）。
    keyword_rows = (
        await db.execute(
            select(
                KeywordHit.id,
                KeywordHit.risk_level,
                KeywordHit.match_type,
                KeywordHit.matched_field,
                KeywordHit.matched_snippet,
                KeywordHit.confidence,
                KeywordCard.name.label("card_name"),
                KeywordTerm.term,
                FlowRecordRow.counterparty_name,
                FlowRecordRow.summary,
                FlowRecordRow.amount,
            )
            .select_from(KeywordHit)
            .join(KeywordCard, KeywordHit.keyword_card_id == KeywordCard.id)
            .join(KeywordTerm, KeywordHit.keyword_term_id == KeywordTerm.id)
            .outerjoin(FlowRecordRow, KeywordHit.flow_record_id == FlowRecordRow.id)
            .where(
                KeywordHit.task_id == task.id,
                KeywordHit.status == "confirmed",
            )
            .order_by(KeywordHit.id.asc())
        )
    ).all()

    keyword_hits: list[dict[str, Any]] = []
    keyword_risk_counts: Counter = Counter()
    keyword_match_type_counts: Counter = Counter()
    for row in keyword_rows:
        keyword_hits.append({
            "id": row.id,
            "card_name": row.card_name,
            "term": row.term,
            "counterparty": row.counterparty_name or "—",
            "amount": row.amount or "—",
            "summary": row.summary or "—",
            "matched_field": row.matched_field,
            "matched_snippet": row.matched_snippet,
            "risk_level": row.risk_level,
            "match_type": row.match_type,
            "confidence": row.confidence,
        })
        keyword_risk_counts[row.risk_level] += 1
        keyword_match_type_counts[row.match_type] += 1

    # cleaning_committed 时间来自 Task.config（S5 清洗提交锁）。
    config = dict(task.config or {}) if task.config else {}
    cleaning_committed = config.get("cleaning_committed")

    return {
        "std_count": std_count,
        "channel_dist": channel_dist,
        "doc_count": doc_count,
        "all_findings": list(findings_rows),
        "findings_total": len(findings_rows),
        "severity_counts": severity_counts,
        "status_counts": status_counts,
        "high_findings": high_findings,
        "balance_findings": balance_findings,
        "keyword_hits": keyword_hits,
        "keyword_total": len(keyword_hits),
        "keyword_risk_counts": keyword_risk_counts,
        "keyword_match_type_counts": keyword_match_type_counts,
        "cleaning_committed": cleaning_committed,
    }


# ---------------------------------------------------------------------------
# LLM agent 上下文切片（按章把聚合数据切成 JSON，数据接地）
# ---------------------------------------------------------------------------


def _finding_to_dict(f: Finding) -> dict:
    """Finding ORM 行 → 可 JSON 序列化的 dict（喂给 agent context）。"""
    return {
        "type": f.type,
        "severity": f.severity,
        "description": f.description,
        "counterparty": f.counterparty,
        "amount": f.amount,
        "confidence": f.confidence,
        "status": f.status,
        "source": f.source,
        "detail_text": f.detail_text,
        "dimension_id": f.dimension_id,
    }


def _task_meta_dict(task: Task) -> dict:
    """Task 元信息 → dict（喂 agent，只放本章要的字段，避免塞无关）。"""
    return {
        "title": task.title,
        "task_id": task.id,
        "status": task.status,
        "employee_name": task.employee_name,
        "employee_id": task.employee_id,
        "department": task.department,
        "audit_start": _fmt_date(task.audit_start),
        "audit_end": _fmt_date(task.audit_end),
        "created_at": _fmt_datetime(task.created_at),
    }


def _slice_chapter_context(chapter_title: str, task: Task, agg: dict) -> str:
    """按章切片聚合数据 → JSON 字符串（每章只放它需要的数据）。

    数据接地硬底线：context 里全是真实聚合数据，agent 围绕它写（禁编造）。
    """
    meta = _task_meta_dict(task)

    if chapter_title == "概述":
        return json.dumps(
            {
                "task": meta,
                "flow_stats": {
                    "standard_count": agg["std_count"],
                    "channel_dist": agg["channel_dist"],
                    "doc_count": agg["doc_count"],
                },
            },
            ensure_ascii=False,
        )

    if chapter_title == "被审查对象":
        return json.dumps(
            {
                "task": {
                    "employee_name": meta["employee_name"],
                    "employee_id": meta["employee_id"],
                    "department": meta["department"],
                    "audit_start": meta["audit_start"],
                    "audit_end": meta["audit_end"],
                }
            },
            ensure_ascii=False,
        )

    if chapter_title == "数据范围":
        return json.dumps(
            {
                "flow_stats": {
                    "standard_count": agg["std_count"],
                    "doc_count": agg["doc_count"],
                    "channel_dist": agg["channel_dist"],
                    "cleaning_committed": agg["cleaning_committed"],
                }
            },
            ensure_ascii=False,
        )

    if chapter_title == "完整性校验（余额）":
        return json.dumps(
            {
                "balance_findings": [
                    _finding_to_dict(f) for f in agg["balance_findings"]
                ],
            },
            ensure_ascii=False,
        )

    if chapter_title == "关键词审查":
        return json.dumps(
            {
                "keyword_total": agg["keyword_total"],
                "keyword_risk_counts": dict(agg["keyword_risk_counts"]),
                "keyword_match_type_counts": dict(agg["keyword_match_type_counts"]),
                "keyword_hits": agg["keyword_hits"],
            },
            ensure_ascii=False,
        )

    if chapter_title == "异常发现汇总":
        return json.dumps(
            {
                "findings_total": agg["findings_total"],
                "severity_counts": dict(agg["severity_counts"]),
                "findings": [
                    _finding_to_dict(f) for f in agg.get("all_findings", [])
                ],
            },
            ensure_ascii=False,
        )

    if chapter_title == "风险评估":
        return json.dumps(
            {
                "findings_total": agg["findings_total"],
                "high_findings": [_finding_to_dict(f) for f in agg["high_findings"]],
                "severity_counts": dict(agg["severity_counts"]),
            },
            ensure_ascii=False,
        )

    if chapter_title == "结论建议":
        return json.dumps(
            {
                "findings_total": agg["findings_total"],
                "high_findings_count": len(agg["high_findings"]),
                "severity_counts": dict(agg["severity_counts"]),
            },
            ensure_ascii=False,
        )

    # 兜底：全量（理论上 8 章都覆盖了）。
    return json.dumps(
        {
            "task": meta,
            "agg": {
                "std_count": agg["std_count"],
                "findings_total": agg["findings_total"],
                "keyword_total": agg["keyword_total"],
            },
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 8 章模板（确定性拼装 Markdown，作 LLM 兜底）
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


def _build_integrity_check(task: Task, agg: dict) -> str:
    """第 3 章 完整性校验（余额）：已采纳的 balance_check 不符列表.

    取 ``Finding where task_id + source='balance_check' + status='accepted'``
    （已采纳的余额不符），逐条列 detail_text。0 条 → 「余额校验通过」。
    """
    balance_findings = agg["balance_findings"]
    lines = [f"## 完整性校验（余额）", ""]
    if not balance_findings:
        lines.append("余额校验通过，未发现不符。")
        lines.append("")
        lines.append(
            "（注：若该任务文档无余额列，如信用卡类流水，则未进行余额校验。）"
        )
        return "\n".join(lines) + "\n"

    lines.append(
        f"已采纳的余额校验不符 {len(balance_findings)} 项："
    )
    lines.append("")
    for f in balance_findings:
        text = (f.detail_text or f.description or "").strip()
        lines.append(f"- {text}")
    lines.append("")
    lines.append("以上不符项均已采纳，建议结合原始凭证核实。")
    return "\n".join(lines) + "\n"


def _build_keyword_review(task: Task, agg: dict) -> str:
    """第 4 章 关键词审查：confirmed 命中汇总 + 明细表.

    汇总：confirmed 命中总数 + 按 risk_level(高/中/低) + 按 match_type 分布。
    明细：关键词 / 对手方 / 金额 / 摘要 / 命中字段 / 命中片段 / 风险等级 /
    匹配类型。无命中 → 空态文案。
    """
    hits = agg["keyword_hits"]
    risk_counts: Counter = agg["keyword_risk_counts"]
    match_type_counts: Counter = agg["keyword_match_type_counts"]

    lines = [f"## 关键词审查", ""]
    if not hits:
        lines.append("关键词审查未发现已确认命中。")
        lines.append("")
        lines.append("（注：仅已确认(confirmed)的关键词命中进入本报告；")
        lines.append("待处理(pending)与已忽略(ignored)的命中不计入。）")
        return "\n".join(lines) + "\n"

    lines.append(f"已确认命中总数：{agg['keyword_total']}")
    lines.append("")
    lines.append("按风险等级分组（灰阶递进，高 > 中 > 低）：")
    lines.append(f"- 高风险：{risk_counts.get('高', 0)} 项")
    lines.append(f"- 中风险：{risk_counts.get('中', 0)} 项")
    lines.append(f"- 低风险：{risk_counts.get('低', 0)} 项")
    lines.append("")
    lines.append("按匹配类型分组：")
    for mt in ("精确匹配", "脱敏匹配", "模糊匹配"):
        lines.append(f"- {mt}：{match_type_counts.get(mt, 0)} 项")
    lines.append("")
    lines.append("已确认命中明细：")
    lines.append("")
    # Markdown 表格（关键词 / 对手方 / 金额 / 命中字段 / 片段 / 风险 / 类型）。
    lines.append(
        "| 关键词 | 对手方 | 金额 | 命中字段 | 命中片段 | 风险等级 | 匹配类型 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for h in hits:
        keyword = f"{h['card_name']}/{h['term']}"
        snippet = (h["matched_snippet"] or "").replace("|", "\\|").replace("\n", " ")
        if len(snippet) > 40:
            snippet = snippet[:40] + "…"
        field_label = "对手方" if h["matched_field"] == "counterparty_name" else "摘要"
        lines.append(
            f"| {keyword} | {h['counterparty']} | {h['amount']} | "
            f"{field_label} | {snippet} | {h['risk_level']} | {h['match_type']} |"
        )
    lines.append("")
    lines.append("（仅已确认(confirmed)的命中计入；pending/ignored 不进本报告。）")
    return "\n".join(lines) + "\n"


def _build_findings_summary(task: Task, agg: dict) -> str:
    """第 5 章 异常发现汇总：已采纳总数 + severity 分组 + status 分组.

    findings 只取 accepted（_aggregate 已过滤），故本章天然只反映已采纳结论。
    """
    sev = agg["severity_counts"]
    st = agg["status_counts"]
    # 灰阶递进描述（高=最深 / 中=中 / 低=浅），禁红黄绿。
    lines = [
        f"## 异常发现汇总",
        "",
        f"- 已采纳异常发现总数：{agg['findings_total']}",
        f"- 按风险等级分组（灰阶递进，高 > 中 > 低）：",
        f"  - 高风险：{sev.get('high', 0)} 项",
        f"  - 中风险：{sev.get('medium', 0)} 项",
        f"  - 低风险：{sev.get('low', 0)} 项",
        "",
        "本章仅汇总已采纳(accepted)的 AI 分析结论；",
        "待处理(pending)与已忽略(ignored)的发现不计入。",
        "",
        "风险等级采用灰阶表述，不使用红黄绿等彩色标识。",
    ]
    return "\n".join(lines) + "\n"


def _build_risk_assessment(task: Task, agg: dict) -> str:
    """第 6 章 风险评估：accepted high severity findings 列表 + 灰阶表述.

    异常条目卡片块：对 accepted high severity findings 发出
    ``> finding: **{type}** | 金额 {amount} | 对手 {counterparty} | {description}``
    行，前端渲染为单色卡片块。findings 只取 accepted（_aggregate 已过滤）。
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
        lines.append("高风险异常发现明细（已采纳）：")
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
        lines.append("暂无已采纳的高风险异常发现。")
    lines.append("")
    lines.append("（仅基于已采纳结论评估；pending/ignored 不影响风险等级。）")
    return "\n".join(lines) + "\n"


def _build_conclusion(task: Task, agg: dict) -> str:
    """第 7 章 结论建议：模板化建议（有 accepted high finding → 重点关注）."""
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
# 公共入口（LLM agent 优先 + 模板兜底）
# ---------------------------------------------------------------------------


def _build_chapter_fallback(
    order_index: int, task: Task, agg: dict
) -> str:
    """按 order_index 取对应的确定性模板兜底 content（prd §一.5 兜底）."""
    builders = [
        lambda: _build_overview(task),
        lambda: _build_subject(task),
        lambda: _build_data_scope(task, agg),
        lambda: _build_integrity_check(task, agg),
        lambda: _build_keyword_review(task, agg),
        lambda: _build_findings_summary(task, agg),
        lambda: _build_risk_assessment(task, agg),
        lambda: _build_conclusion(task, agg),
    ]
    if 0 <= order_index < len(builders):
        return builders[order_index]()
    return ""


async def build_all_chapters(
    db: AsyncSession, task: Task, *, report_model: Optional[LLMModel] = None
) -> list[str]:
    """聚合数据 → 每章 run_chapter 产 LLM markdown（失败回退模板）.

    每章：``try: content = await run_chapter(...) except: content = _build_*``。
    单章 agent 失败不阻塞其他章（prd §六风险）。

    Args:
        db: 异步 DB session。
        task: 任务 ORM 行。
        report_model: report_generation 阶段指派卡片（None → 调用方应先取卡片传入；
            传 None 时 agent 内部回退 env settings）。

    Returns:
        8 章 Markdown content 列表（按固定 order_index 顺序）。
    """
    agg = await _aggregate(db, task)
    titles = chapter_titles()
    contents: list[str] = []

    for idx, _title in enumerate(titles):
        contents.append(
            await build_chapter_content(
                db, task, idx, report_model=report_model, agg=agg
            )
        )

    return contents


async def build_chapter_content(
    db: AsyncSession,
    task: Task,
    order_index: int,
    *,
    report_model: Optional[LLMModel] = None,
    agg: Optional[dict] = None,
) -> str:
    """生成单章正文；可传入预聚合 ``agg`` 以支持后台逐章写回。

    这是 ``build_all_chapters`` / ``build_one_chapter`` 的共享实现。异步报告
    job 会先聚合一次，再逐章调用本函数，确保每章 LLM 完成后能立即写回 DB。
    """
    titles = chapter_titles()
    if not (0 <= order_index < len(titles)):
        return ""

    if agg is None:
        agg = await _aggregate(db, task)

    title = titles[order_index]
    context_json = _slice_chapter_context(title, task, agg)
    deps = ReportDeps(db=db, task_id=task.id)
    try:
        content = await run_chapter(deps, title, context_json, model=report_model)
        logger.info("报告章节「%s」(idx=%s) LLM 生成成功", title, order_index)
    except Exception as exc:
        logger.warning(
            "报告章节「%s」(idx=%s) LLM 生成失败，回退模板: %s",
            title,
            order_index,
            exc,
        )
        content = _build_chapter_fallback(order_index, task, agg)
    return content


async def build_one_chapter(
    db: AsyncSession, task: Task, order_index: int,
    *, report_model: Optional[LLMModel] = None,
) -> str:
    """单章重生成：run_chapter 单章（失败回退模板）.

    Args:
        db: 异步 DB session。
        task: 任务 ORM 行。
        order_index: 章节 order_index（0-7）。
        report_model: report_generation 阶段指派卡片。
    """
    return await build_chapter_content(
        db, task, order_index, report_model=report_model
    )
