# -*- coding: utf-8 -*-
"""报告融合上游 + Word/PDF 封面与目录 tests（06-28-report-fusion-word-cover）.

Covers (per prd §验证):
* _aggregate: findings accepted 过滤（pending/ignored 不计）；keyword confirmed
  聚合 + card/term 名 join；balance_check accepted 聚合。
* _build_keyword_review / _build_integrity_check 产物含汇总 + 明细 / 空态。
* 章节顺序 + 数量（8 章）。
* 封面 + 目录渲染 smoke（docx/pdf 不崩，能生成文件）。
"""

from datetime import datetime
from pathlib import Path

import pytest

from app.models import (
    Finding,
    FlowRecordRow,
    KeywordCard,
    KeywordHit,
    KeywordTerm,
    Report,
    Task,
)
from app.services.export_service import ExportService
from app.services.report_chapter_builder import (
    _aggregate,
    _build_integrity_check,
    _build_keyword_review,
    build_all_chapters,
    chapter_titles,
)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_task(session, user_id: int) -> Task:
    """Seed a completed task owned by user_id with employee metadata + config."""
    task = Task(
        title="报告融合测试任务",
        owner_id=user_id,
        status="completed",
        config={"cleaning_committed": "2026-06-20 10:00"},
        employee_name="张三",
        employee_id="EMP001",
        department="审计部",
        audit_start=datetime(2026, 1, 1),
        audit_end=datetime(2026, 6, 30),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def _seed_flow_record(session, task_id: int, counterparty="某公司", amount="5000.00") -> FlowRecordRow:
    rec = FlowRecordRow(
        task_id=task_id,
        record_type="standard",
        row_index=1,
        is_valid=True,
        transaction_time="2026-01-15 10:00:00",
        counterparty_name=counterparty,
        counterparty_account="ACC123",
        amount=amount,
        raw_amount=amount,
        summary="货款",
        transaction_type="收入",
        raw_payload={},
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec


async def _seed_findings(session, task_id: int) -> None:
    """Seed findings: 1 accepted high + 1 pending (not counted) + 1 balance_check accepted."""
    session.add_all([
        Finding(
            task_id=task_id,
            type="大额异常",
            severity="high",
            description="单笔大额交易",
            counterparty="某公司",
            amount="50000.00",
            confidence=0.9,
            status="accepted",
            source="rule",
        ),
        # pending → 不进报告.
        Finding(
            task_id=task_id,
            type="待复核",
            severity="medium",
            description="待复核项",
            counterparty="其他",
            amount="1000.00",
            confidence=0.5,
            status="pending",
            source="rule",
        ),
        # balance_check accepted → 进完整性校验章.
        Finding(
            task_id=task_id,
            type="余额不符",
            severity="high",
            description="首条余额不符",
            confidence=1.0,
            status="accepted",
            source="balance_check",
            detail_text="文档A 首条余额 10000，期望 10500，差 -500",
        ),
        # balance_check pending → 不进报告.
        Finding(
            task_id=task_id,
            type="余额不符",
            severity="high",
            description="待复核余额",
            confidence=1.0,
            status="pending",
            source="balance_check",
            detail_text="不应出现在报告的余额校验项",
        ),
    ])
    await session.commit()


async def _seed_keyword_hits(session, task_id: int, flow_record_id: int) -> None:
    """Seed a keyword card + term + 2 confirmed hits + 1 pending hit (not counted)."""
    card = KeywordCard(name="敏感词卡", risk_level="高", note="高风险敏感词")
    term = KeywordTerm(term="敏感词")
    card.terms.append(term)
    session.add(card)
    await session.commit()
    await session.refresh(card)
    await session.refresh(term)

    session.add_all([
        # confirmed → 进报告.
        KeywordHit(
            task_id=task_id,
            flow_record_id=flow_record_id,
            keyword_card_id=card.id,
            keyword_term_id=term.id,
            match_type="精确匹配",
            confidence=95,
            risk_level="高",
            matched_field="counterparty_name",
            matched_snippet="某敏感词公司",
            status="confirmed",
        ),
        KeywordHit(
            task_id=task_id,
            flow_record_id=flow_record_id,
            keyword_card_id=card.id,
            keyword_term_id=term.id,
            match_type="模糊匹配",
            confidence=70,
            risk_level="中",
            matched_field="summary",
            matched_snippet="含敏感词摘要",
            status="confirmed",
        ),
        # pending → 不进报告.
        KeywordHit(
            task_id=task_id,
            flow_record_id=flow_record_id,
            keyword_card_id=card.id,
            keyword_term_id=term.id,
            match_type="精确匹配",
            confidence=80,
            risk_level="低",
            matched_field="summary",
            matched_snippet="待复核命中",
            status="pending",
        ),
    ])
    await session.commit()


# ---------------------------------------------------------------------------
# _aggregate: findings accepted 过滤 + keyword confirmed + balance_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_filters_findings_to_accepted_only(db_session):
    """_aggregate findings 只取 accepted（pending/ignored 不计）."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    await _seed_findings(session, task.id)

    agg = await _aggregate(session, task)
    # accepted findings = 1 high rule + 1 balance_check = 2.
    assert agg["findings_total"] == 2
    # pending 的 rule finding 不计.
    assert agg["severity_counts"]["high"] == 2
    assert agg["severity_counts"].get("medium", 0) == 0
    # high_findings 含 2 条（rule + balance_check 都是 high severity accepted）.
    assert len(agg["high_findings"]) == 2


@pytest.mark.asyncio
async def test_aggregate_balance_findings_accepted_only(db_session):
    """_aggregate balance_findings 只取 accepted 的 source=balance_check."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    await _seed_findings(session, task.id)

    agg = await _aggregate(session, task)
    # 只 1 条 accepted balance_check（pending 那条不计）.
    assert len(agg["balance_findings"]) == 1
    assert agg["balance_findings"][0].detail_text.startswith("文档A 首条余额")


@pytest.mark.asyncio
async def test_aggregate_keyword_hits_confirmed_with_card_term_join(db_session):
    """_aggregate keyword_hits 只取 confirmed + join card/term 取名（一次 join）."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    rec = await _seed_flow_record(session, task.id)
    await _seed_keyword_hits(session, task.id, rec.id)

    agg = await _aggregate(session, task)
    # 只 2 条 confirmed（pending 不计）.
    assert agg["keyword_total"] == 2
    assert len(agg["keyword_hits"]) == 2
    # card/term 名 join 正确.
    assert all(h["card_name"] == "敏感词卡" for h in agg["keyword_hits"])
    assert all(h["term"] == "敏感词" for h in agg["keyword_hits"])
    # 风险等级分组正确（1 高 + 1 中）.
    assert agg["keyword_risk_counts"]["高"] == 1
    assert agg["keyword_risk_counts"]["中"] == 1
    # 匹配类型分组正确（1 精确 + 1 模糊）.
    assert agg["keyword_match_type_counts"]["精确匹配"] == 1
    assert agg["keyword_match_type_counts"]["模糊匹配"] == 1
    # 金额从关联 flow_record join 取.
    assert any(h["amount"] == "5000.00" for h in agg["keyword_hits"])


@pytest.mark.asyncio
async def test_aggregate_empty_task(db_session):
    """_aggregate 空任务（无 findings/keyword/records）返 0 计数."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    agg = await _aggregate(session, task)
    assert agg["findings_total"] == 0
    assert agg["keyword_total"] == 0
    assert len(agg["balance_findings"]) == 0
    assert len(agg["high_findings"]) == 0


# ---------------------------------------------------------------------------
# _build_keyword_review / _build_integrity_check 产物
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_keyword_review_with_hits(db_session):
    """_build_keyword_review 含汇总 + 明细表."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    rec = await _seed_flow_record(session, task.id)
    await _seed_keyword_hits(session, task.id, rec.id)
    agg = await _aggregate(session, task)

    content = _build_keyword_review(task, agg)
    assert "关键词审查" in content
    # 汇总总数.
    assert "已确认命中总数：2" in content
    # 风险等级汇总.
    assert "高风险：1 项" in content
    assert "中风险：1 项" in content
    # 匹配类型汇总.
    assert "精确匹配：1 项" in content
    assert "模糊匹配：1 项" in content
    # 明细表表头.
    assert "| 关键词 | 对手方 | 金额 | 命中字段 | 命中片段 | 风险等级 | 匹配类型 |" in content
    # 明细含 card/term 名.
    assert "敏感词卡/敏感词" in content


@pytest.mark.asyncio
async def test_build_keyword_review_empty_state(db_session):
    """_build_keyword_review 无命中显空态."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    agg = await _aggregate(session, task)

    content = _build_keyword_review(task, agg)
    assert "关键词审查未发现已确认命中" in content


@pytest.mark.asyncio
async def test_build_integrity_check_with_findings(db_session):
    """_build_integrity_check 含 accepted balance_check 明细."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    await _seed_findings(session, task.id)
    agg = await _aggregate(session, task)

    content = _build_integrity_check(task, agg)
    assert "完整性校验（余额）" in content
    assert "已采纳的余额校验不符 1 项" in content
    # pending 的余额校验项不出现.
    assert "文档A 首条余额" in content
    assert "不应出现在报告的余额校验项" not in content


@pytest.mark.asyncio
async def test_build_integrity_check_empty_state(db_session):
    """_build_integrity_check 无 balance_check 显通过."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    agg = await _aggregate(session, task)

    content = _build_integrity_check(task, agg)
    assert "余额校验通过，未发现不符" in content


# ---------------------------------------------------------------------------
# 章节顺序 + 数量（8 章）
# ---------------------------------------------------------------------------


def test_chapter_titles_returns_eight_in_order():
    """chapter_titles 返 8 章 + 正确顺序."""
    titles = chapter_titles()
    assert len(titles) == 8
    assert titles == [
        "概述", "被审查对象", "数据范围", "完整性校验（余额）",
        "关键词审查", "异常发现汇总", "风险评估", "结论建议",
    ]


@pytest.mark.asyncio
async def test_build_all_chapters_returns_eight(db_session):
    """build_all_chapters 返 8 章 content."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    chapters = await build_all_chapters(session, task)
    assert len(chapters) == 8


# ---------------------------------------------------------------------------
# 封面 + 目录渲染 smoke（docx/pdf 不崩，能生成文件）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_report_docx_cover_and_toc_smoke(client, db_session, temp_output_dir):
    """导出 docx 含封面 + 目录 + 各章，不崩且生成文件."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    # 走 API 生成报告（建 8 章）.
    resp = await client.post(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 200
    report = await session.get(Report, resp.json()["id"])
    report.status = "generated"
    await session.commit()

    export_resp = await client.post(
        f"/api/tasks/{task.id}/export/report",
        json={"format": "docx", "include_annotations": False},
    )
    assert export_resp.status_code == 200
    path = Path(export_resp.json()["file_path"])
    assert path.exists()
    assert path.suffix == ".docx"
    # 文件非空.
    assert path.stat().st_size > 0


@pytest.mark.asyncio
async def test_export_report_pdf_cover_and_toc_smoke(client, db_session, temp_output_dir):
    """导出 pdf 含封面 + 目录 + 各章，不崩且生成文件."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    resp = await client.post(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 200
    report = await session.get(Report, resp.json()["id"])
    report.status = "generated"
    await session.commit()

    export_resp = await client.post(
        f"/api/tasks/{task.id}/export/report",
        json={"format": "pdf", "include_annotations": False},
    )
    assert export_resp.status_code == 200
    path = Path(export_resp.json()["file_path"])
    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.stat().st_size > 0


@pytest.mark.asyncio
async def test_export_report_html_cover_smoke(client, db_session, temp_output_dir):
    """导出 html 含封面，不崩且含封面大标题."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    resp = await client.post(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 200
    report = await session.get(Report, resp.json()["id"])
    report.status = "generated"
    await session.commit()

    export_resp = await client.post(
        f"/api/tasks/{task.id}/export/report",
        json={"format": "html", "include_annotations": False},
    )
    assert export_resp.status_code == 200
    path = Path(export_resp.json()["file_path"])
    content = path.read_text(encoding="utf-8")
    # 封面大标题.
    assert "银行/支付流水审查报告" in content
    # 元信息块含被审查人.
    assert "被审查人：张三 · EMP001 · 审计部" in content


# ---------------------------------------------------------------------------
# 封面元信息块缺项跳过
# ---------------------------------------------------------------------------


def test_cover_meta_lines_skips_missing_fields():
    """_cover_meta_lines 缺项跳过（无被审查人时跳过该行）."""
    from app.models import Task

    task = Task(
        title="t",
        owner_id=1,
        status="completed",
        # 无 employee 字段 → 被审查人行跳过.
    )
    from app.services.export_service import ExportService

    lines = ExportService._cover_meta_lines(task)
    # 无被审查人行.
    assert not any(l.startswith("被审查人") for l in lines)
    # 仍有生成日期 + 任务编号.
    assert any(l.startswith("生成日期") for l in lines)
    assert any(l.startswith("任务编号") for l in lines)
