# -*- coding: utf-8 -*-
"""余额防篡改校验单测（06-28-balance-column-check）.

覆盖 PRD §四（首尾锚点 + 时分秒 gate）+ §八验收：
- 校验算法纯逻辑（check_balance_totals）：①相符不产 ②改金额→不符 ③删/增行→不符
  ④方向不明行不计入 net ⑤无时分秒跳过 ⑥无余额列跳过 ⑦不足 2 行跳过 ⑧容差边界
  ⑨时序（传入乱序，函数内按时序排）。
- portrait：9 字段词表（balance 可映射）。
- normalizer balance 抽取：余额列数据保留（is_valid=true）+ 余额汇总行过滤（is_valid=false）。
- run_balance_check：有/无余额列、时分秒 gate、重跑清旧、多文档不覆盖。
"""

import pytest
from sqlalchemy import select

from app.llm.portrait import SYSTEM_PROMPT_DOCUMENT_PORTRAIT
from app.llm.normalizer import SYSTEM_PROMPT_DATA_NORMALIZER
from app.models import Document, Finding, FlowRecordRow, Task
from app.services.audit.balance_check import (
    BalanceTotalsRow,
    _has_hms,
    _row_has_balance_column,
    check_balance_totals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(idx, ttime, balance, amount, ttype):
    """Build a BalanceTotalsRow (id for identity, ttime carries hms)."""
    return BalanceTotalsRow(
        id=idx,
        transaction_time=ttime,
        balance=balance,
        amount=amount,
        transaction_type=ttype,
    )


# ---------------------------------------------------------------------------
# check_balance_totals — 纯逻辑（PRD §四 首尾锚点对账）
# ---------------------------------------------------------------------------


def test_balance_totals_consistent_no_finding():
    """① 相符：首条余额 + 后续净收支 = 末条余额 → 不产 finding。

    B1=1000, net=(+100 -200 -50)=-150, expected=850, BN=850 → 相符。
    """
    rows = [
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
        _row(3, "2026-06-01 12:00:00", "900.00", "200.00", "支出"),
        _row(4, "2026-06-01 13:00:00", "850.00", "50.00", "支出"),
    ]
    assert check_balance_totals(rows) is None


def test_balance_totals_changed_amount_flags():
    """② 改一金额 → net 变 → expected 偏 → 不符，产 1 条 finding。

    B1=1000, net=(+100 -150)=-50, expected=950, BN=900 → 差 -50 → 不符。
    """
    rows = [
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
        _row(3, "2026-06-01 12:00:00", "900.00", "150.00", "支出"),  # 篡改：200→150
    ]
    finding = check_balance_totals(rows)
    assert finding is not None
    assert "首条余额" in finding.detail_text
    assert "净收支" in finding.detail_text
    assert "期望末条" in finding.detail_text
    assert "实际末条" in finding.detail_text
    assert "差" in finding.detail_text
    assert finding.amount == "¥50.00"  # abs(net)=50


def test_balance_totals_deleted_row_flags():
    """③ 删/增行 → 求和项变 → net 变 → 不符。

    原本 4 行链连续；删掉中间一行后求和项变，expected 偏离 BN。
    构造：B1=1000, 保留收入+100、删掉支出-200、保留支出-50 → net=+50,
    expected=1050, BN=850 → 不符。
    """
    rows = [
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
        # 第3行（支出200）被删 → 求和里没了它
        _row(4, "2026-06-01 13:00:00", "850.00", "50.00", "支出"),
    ]
    finding = check_balance_totals(rows)
    assert finding is not None


def test_balance_totals_unknown_direction_excluded_from_net():
    """④ 方向不明（transaction_type 非收/支）不计入 net（保守跳过）。

    第2行方向不明 → 不计入 net。B1=1000, net=0（只剩不明行）, expected=1000,
    BN=900 → 不符（不明行的金额被忽略，链断）。
    """
    rows = [
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "900.00", "100.00", "不明"),  # 不计入
    ]
    finding = check_balance_totals(rows)
    # net=0, expected=1000, BN=900 → 差 -100 → 不符
    assert finding is not None
    # 明确不明行的 100 没进 net
    assert "净收支 +0.00" in finding.detail_text


def test_balance_totals_insufficient_rows_skips():
    """⑦ 不足 2 条 hms+balance 行 → 返 None（默认通过）。"""
    assert check_balance_totals([]) is None
    assert check_balance_totals(
        [_row(1, "2026-06-01 10:00:00", "1000.00", "", "")]
    ) is None


def test_balance_totals_tolerance_boundary():
    """⑧ 容差边界：差 = tol 不报（≤ 容差），略大报。

    tol = max(0.01, 0.0001*|BN|)。
    case A: BN=1000.01, B1=1000, net=0 → expected=1000, tol=max(0.01,0.1)=0.1,
    差 0.01 ≤ 0.1 → 不报。
    case B: BN=1000.02, 差 0.02 ≤ 0.1 → 不报（容差内）。
    case C: BN=1010, 差 10 > 0.1 → 报。
    """
    # 容差内（相对容差 0.0001*1000.01≈0.1 主导）
    rows_a = [
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "1000.02", "", ""),
    ]
    assert check_balance_totals(rows_a) is None

    # 超容差
    rows_c = [
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "1010.00", "", ""),
    ]
    assert check_balance_totals(rows_c) is not None


def test_balance_totals_absolute_tolerance_for_small_balance():
    """⑧ 绝对容差 0.01 主导（小金额场景）：BN 小时 tol=0.01。

    BN=0.005 → tol=max(0.01, ~0)=0.01。差 0.005 ≤ 0.01 → 不报。
    """
    rows = [
        _row(1, "2026-06-01 10:00:00", "0.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "0.005", "", ""),
    ]
    assert check_balance_totals(rows) is None


def test_balance_totals_sorts_by_transaction_time():
    """⑨ 时序：行传入乱序，函数按时序排后正确对账。

    乱序传入（row_index 与时间序不一致），函数按 parse_datetime 升序排。
    排好后：B1=1000(10:00), net=(+100-200)=-100, expected=900,
    BN=900(12:00) → 相符 → None。
    若不排（按传入 row_index 序），会拿错首尾 → 这里验证排序生效。
    """
    rows = [
        _row(3, "2026-06-01 12:00:00", "900.00", "200.00", "支出"),   # 末条
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),            # 首条
        _row(2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
    ]
    finding = check_balance_totals(rows)
    assert finding is None  # 排序后相符


def test_balance_totals_sort_order_changes_result():
    """⑨ 强化：同一组行，乱序传入也能定位正确首尾，差异被检出。

    乱序传入，排好后 B1=1000, net=-100, expected=900, BN=800 → 不符。
    """
    rows = [
        _row(3, "2026-06-01 12:00:00", "800.00", "200.00", "支出"),
        _row(1, "2026-06-01 10:00:00", "1000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
    ]
    finding = check_balance_totals(rows)
    assert finding is not None


def test_balance_totals_thousands_separator_parsed():
    """千分位金额/余额解析：parse_amount 剥逗号正确参与运算。"""
    rows = [
        _row(1, "2026-06-01 10:00:00", "10,000.00", "", ""),
        _row(2, "2026-06-01 11:00:00", "11,234.56", "1,234.56", "收入"),
    ]
    # B1=10000, net=+1234.56, expected=11234.56, BN=11234.56 → 相符
    assert check_balance_totals(rows) is None


# ---------------------------------------------------------------------------
# _has_hms — 时分秒判定（剔 00:00:00 / 只日期）
# ---------------------------------------------------------------------------


def test_has_hms_with_nonzero_time():
    assert _has_hms("2026-06-01 10:30:00") is True


def test_has_hms_zero_time_is_noise():
    assert _has_hms("2026-06-01 00:00:00") is False


def test_has_hms_date_only():
    assert _has_hms("2026-06-01") is False


def test_has_hms_empty_or_none():
    assert _has_hms("") is False
    assert _has_hms(None) is False


# ---------------------------------------------------------------------------
# _row_has_balance_column — portrait.column_mapping 判定
# ---------------------------------------------------------------------------


def test_row_has_balance_column_string_entry():
    assert _row_has_balance_column(["transaction_time", "amount", "balance"]) is True


def test_row_has_balance_column_array_entry():
    assert _row_has_balance_column(["transaction_time", ["amount", "balance"]]) is True


def test_row_has_balance_column_absent():
    assert (
        _row_has_balance_column(["transaction_time", "amount", "summary"]) is False
    )


def test_row_has_balance_column_empty():
    assert _row_has_balance_column([]) is False
    assert _row_has_balance_column(None) is False


# ---------------------------------------------------------------------------
# Portrait prompt — 9 字段词表（balance 可映射）
# ---------------------------------------------------------------------------


def test_portrait_prompt_mentions_balance_field():
    """portrait 提示词「映射指导」段含 9 字段，含 balance + 余额表头映射指导。"""
    assert "balance" in SYSTEM_PROMPT_DOCUMENT_PORTRAIT
    # 映射指导段写明「余额/账户余额/当前余额/结余」→ balance
    assert "余额" in SYSTEM_PROMPT_DOCUMENT_PORTRAIT
    assert "9个标准字段" in SYSTEM_PROMPT_DOCUMENT_PORTRAIT
    # few-shot column_mapping 样例含 balance
    assert SYSTEM_PROMPT_DOCUMENT_PORTRAIT.count('"balance"') >= 1


# ---------------------------------------------------------------------------
# Normalizer prompt — balance 抽取 + 余额列 vs 汇总行区分
# ---------------------------------------------------------------------------


def test_normalizer_prompt_has_balance_field_and_noise_rule():
    """normalizer 提示词含 balance 标准字段 + 余额列 vs 余额汇总行区分判据。"""
    # 标准字段段含 balance
    assert "balance" in SYSTEM_PROMPT_DATA_NORMALIZER
    assert "账户余额" in SYSTEM_PROMPT_DATA_NORMALIZER
    # 坑判据：余额列逐行数据保留 vs 余额汇总行过滤
    assert "余额列" in SYSTEM_PROMPT_DATA_NORMALIZER or "余额**列**" in SYSTEM_PROMPT_DATA_NORMALIZER
    assert "汇总" in SYSTEM_PROMPT_DATA_NORMALIZER
    # JSON 样例含 balance
    assert '"balance"' in SYSTEM_PROMPT_DATA_NORMALIZER


# ---------------------------------------------------------------------------
# run_balance_check — 异步 DB 集成
# ---------------------------------------------------------------------------


async def _seed_balance_task_doc(session, user, *, with_balance_column: bool):
    """Seed a Task + Document (with optional balance column_mapping)."""
    task = Task(
        title="balance test",
        status="completed",
        owner_id=user.id,
        config={},
    )
    session.add(task)
    await session.flush()

    column_mapping = (
        ["transaction_time", "amount", "transaction_type", "balance"]
        if with_balance_column
        else ["transaction_time", "amount", "transaction_type"]
    )
    doc = Document(
        task_id=task.id,
        filename="stmt.xlsx",
        original_path="stmt.xlsx",
        status="completed",
        flow_tables={"records": []},
        portrait={
            "account_type": "bank_general",
            "column_mapping": column_mapping,
        },
    )
    session.add(doc)
    await session.flush()
    return task, doc


def _std_row(task_id, doc_id, idx, ttime, balance, amount, ttype):
    """Build a standard FlowRecordRow with hms transaction_time."""
    return FlowRecordRow(
        task_id=task_id, document_id=doc_id, record_type="standard",
        row_index=idx, is_valid=True, balance=balance, amount=amount,
        transaction_type=ttype, transaction_time=ttime,
    )


@pytest.mark.asyncio
async def test_run_balance_check_no_balance_column_skips(db_session):
    """无余额列文档：run_balance_check 跳过，返回 [] 不报错、不落 finding。"""
    session, user = db_session
    task, doc = await _seed_balance_task_doc(session, user, with_balance_column=False)
    session.add(
        _std_row(task.id, doc.id, 1, "2026-06-01 10:00:00", "1000.00", "100.00", "收入")
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings = await run_balance_check(session, task.id, doc.id)
    assert findings == []


@pytest.mark.asyncio
async def test_run_balance_check_no_hms_skips(db_session):
    """无时分秒行（只日期 / 00:00:00）→ 整文档跳过（默认通过，不报错）。

    PRD §四 gate：无时分秒 → 默认通过、跳过不报错。
    """
    session, user = db_session
    task, doc = await _seed_balance_task_doc(session, user, with_balance_column=True)
    session.add_all(
        [
            FlowRecordRow(
                task_id=task.id, document_id=doc.id, record_type="standard",
                row_index=1, is_valid=True, balance="1000.00", amount="", transaction_type="",
                transaction_time="2026-06-01",  # 只日期，无 hms
            ),
            FlowRecordRow(
                task_id=task.id, document_id=doc.id, record_type="standard",
                row_index=2, is_valid=True, balance="800.00", amount="200.00", transaction_type="支出",
                transaction_time="2026-06-02 00:00:00",  # 00:00:00 噪音
            ),
        ]
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings = await run_balance_check(session, task.id, doc.id)
    assert findings == []


@pytest.mark.asyncio
async def test_run_balance_check_persists_finding_with_source(db_session):
    """有余额列 + 有时分秒行 + 对账不符：落 1 条文档级 finding。

    B1=1000, net=(+100-200)=-100, expected=900, BN=800 → 不符。
    """
    session, user = db_session
    task, doc = await _seed_balance_task_doc(session, user, with_balance_column=True)
    session.add_all(
        [
            _std_row(task.id, doc.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
            _std_row(task.id, doc.id, 2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
            # 不符：expected=900, BN=800
            _std_row(task.id, doc.id, 3, "2026-06-01 12:00:00", "800.00", "200.00", "支出"),
        ]
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings = await run_balance_check(session, task.id, doc.id)
    await session.commit()

    assert len(findings) == 1
    assert findings[0].source == "balance_check"
    assert findings[0].type == "余额不符"
    assert findings[0].severity == "medium"
    assert findings[0].confidence == 1.0
    assert findings[0].status == "pending"
    assert findings[0].document_id == doc.id
    # 文档级 aggregate：无单行证据、无对手方
    assert findings[0].evidence_record_ids == []
    assert findings[0].counterparty is None
    assert findings[0].amount == "¥100.00"

    db_findings = (
        await session.execute(
            select(Finding).where(Finding.task_id == task.id, Finding.source == "balance_check")
        )
    ).scalars().all()
    assert len(db_findings) == 1


@pytest.mark.asyncio
async def test_run_balance_check_consistent_no_finding(db_session):
    """有余额列 + 有时分秒行 + 对账相符：不落 finding。"""
    session, user = db_session
    task, doc = await _seed_balance_task_doc(session, user, with_balance_column=True)
    session.add_all(
        [
            _std_row(task.id, doc.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
            _std_row(task.id, doc.id, 2, "2026-06-01 11:00:00", "1100.00", "100.00", "收入"),
            _std_row(task.id, doc.id, 3, "2026-06-01 12:00:00", "900.00", "200.00", "支出"),
        ]
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings = await run_balance_check(session, task.id, doc.id)
    assert findings == []


@pytest.mark.asyncio
async def test_run_balance_check_rerun_clears_old_findings(db_session):
    """重跑：先删该文档 source='balance_check' 旧 finding 再重算（行可能变了）。"""
    session, user = db_session
    task, doc = await _seed_balance_task_doc(session, user, with_balance_column=True)
    rows = [
        _std_row(task.id, doc.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
        # 不符：net=-200, expected=800, BN=700
        _std_row(task.id, doc.id, 2, "2026-06-01 11:00:00", "700.00", "200.00", "支出"),
    ]
    session.add_all(rows)
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    first = await run_balance_check(session, task.id, doc.id)
    await session.commit()
    assert len(first) == 1

    # 修正末条余额让对账相符：expected=800, BN=800
    rows[1].balance = "800.00"
    await session.commit()

    second = await run_balance_check(session, task.id, doc.id)
    await session.commit()
    assert second == []

    db_findings = (
        await session.execute(
            select(Finding).where(Finding.task_id == task.id, Finding.source == "balance_check")
        )
    ).scalars().all()
    assert db_findings == []


@pytest.mark.asyncio
async def test_run_balance_check_insufficient_hms_rows_skips(db_session):
    """不足 2 条 hms+balance 行 → 跳过（默认通过）。"""
    session, user = db_session
    task, doc = await _seed_balance_task_doc(session, user, with_balance_column=True)
    session.add(
        _std_row(task.id, doc.id, 1, "2026-06-01 10:00:00", "1000.00", "", "")
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings = await run_balance_check(session, task.id, doc.id)
    assert findings == []


# ---------------------------------------------------------------------------
# API: GET /findings source 过滤（AI 分析页不污染 balance_check）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_findings_api_excludes_balance_check_by_default(client, db_session):
    """默认 GET /findings 不返回 balance_check finding（AI 分析页维度视图）。"""
    session, user = db_session
    task = Task(title="filter", owner_id=user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    session.add_all(
        [
            Finding(
                task_id=task.id, type="大额", severity="high", description="d",
                confidence=0.9, status="pending", source="rule",
            ),
            Finding(
                task_id=task.id, type="余额不符", severity="medium", description="b",
                confidence=1.0, status="pending", source="balance_check",
            ),
        ]
    )
    await session.commit()

    resp = await client.get(f"/api/tasks/{task.id}/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "rule"


@pytest.mark.asyncio
async def test_findings_api_source_filter_returns_balance_check(client, db_session):
    """GET /findings?source=balance_check 单独取余额校验不符（clean 页校验区）。"""
    session, user = db_session
    task = Task(title="filter2", owner_id=user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    session.add_all(
        [
            Finding(
                task_id=task.id, type="大额", severity="high", description="d",
                confidence=0.9, status="pending", source="rule",
            ),
            Finding(
                task_id=task.id, type="余额不符", severity="medium", description="b",
                confidence=1.0, status="pending", source="balance_check",
            ),
        ]
    )
    await session.commit()

    resp = await client.get(f"/api/tasks/{task.id}/findings?source=balance_check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "balance_check"
    assert data["items"][0]["type"] == "余额不符"


# ---------------------------------------------------------------------------
# 多文档场景（必修 bug 回归）：多文档任务 / append 不互相覆盖
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_balance_check_multi_document_no_clobber(db_session):
    """多文档任务：A/B 两个有余额列文档各自校验，互不覆盖（必修 bug 回归）。

    旧 bug：run_balance_check 按任务级删 source='balance_check' finding → 每跑一个
    文档就删光整个任务的余额校验结果，最后只剩最后一个文档的。修复后按 document_id
    范围删，两文档的不符 finding 都在。
    """
    session, user = db_session
    task = Task(title="multi-doc", status="completed", owner_id=user.id, config={})
    session.add(task)
    await session.flush()

    def _portrait():
        return {
            "account_type": "bank_general",
            "column_mapping": ["transaction_time", "amount", "transaction_type", "balance"],
        }

    doc_a = Document(
        task_id=task.id, filename="a.xlsx", original_path="a.xlsx",
        status="completed", flow_tables={"records": []}, portrait=_portrait(),
    )
    doc_b = Document(
        task_id=task.id, filename="b.xlsx", original_path="b.xlsx",
        status="completed", flow_tables={"records": []}, portrait=_portrait(),
    )
    session.add_all([doc_a, doc_b])
    await session.flush()

    session.add_all(
        [
            _std_row(task.id, doc_a.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
            # A 不符：expected=800, BN=700
            _std_row(task.id, doc_a.id, 2, "2026-06-01 11:00:00", "700.00", "200.00", "支出"),
            _std_row(task.id, doc_b.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
            # B 不符：expected=800, BN=900
            _std_row(task.id, doc_b.id, 2, "2026-06-01 11:00:00", "900.00", "200.00", "支出"),
        ]
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings_a = await run_balance_check(session, task.id, doc_a.id)
    findings_b = await run_balance_check(session, task.id, doc_b.id)
    await session.commit()

    assert len(findings_a) == 1
    assert findings_a[0].document_id == doc_a.id
    assert len(findings_b) == 1
    assert findings_b[0].document_id == doc_b.id

    db_findings = (
        await session.execute(
            select(Finding).where(
                Finding.task_id == task.id,
                Finding.source == "balance_check",
            )
        )
    ).scalars().all()
    assert len(db_findings) == 2
    doc_ids = {f.document_id for f in db_findings}
    assert doc_ids == {doc_a.id, doc_b.id}


@pytest.mark.asyncio
async def test_run_balance_check_append_preserves_old_doc(db_session):
    """append 场景：对新文档跑校验不删旧文档的余额校验 finding。

    旧 bug：任务级删除 → append 新文档时把旧文档的校验结果也删了。修复后按
    document_id 范围删，只动新文档。
    """
    session, user = db_session
    task = Task(title="append", status="completed", owner_id=user.id, config={})
    session.add(task)
    await session.flush()

    def _portrait():
        return {
            "account_type": "bank_general",
            "column_mapping": ["transaction_time", "amount", "transaction_type", "balance"],
        }

    doc_old = Document(
        task_id=task.id, filename="old.xlsx", original_path="old.xlsx",
        status="completed", flow_tables={"records": []}, portrait=_portrait(),
    )
    session.add(doc_old)
    await session.flush()
    session.add_all(
        [
            _std_row(task.id, doc_old.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
            # 旧文档不符：expected=800, BN=700
            _std_row(task.id, doc_old.id, 2, "2026-06-01 11:00:00", "700.00", "200.00", "支出"),
        ]
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    old_findings = await run_balance_check(session, task.id, doc_old.id)
    await session.commit()
    assert len(old_findings) == 1

    doc_new = Document(
        task_id=task.id, filename="new.xlsx", original_path="new.xlsx",
        status="completed", flow_tables={"records": []}, portrait=_portrait(),
    )
    session.add(doc_new)
    await session.flush()
    session.add_all(
        [
            _std_row(task.id, doc_new.id, 1, "2026-06-01 10:00:00", "500.00", "", ""),
            # 新文档不符：expected=400, BN=200
            _std_row(task.id, doc_new.id, 2, "2026-06-01 11:00:00", "200.00", "100.00", "支出"),
        ]
    )
    await session.commit()

    new_findings = await run_balance_check(session, task.id, doc_new.id)
    await session.commit()
    assert len(new_findings) == 1
    assert new_findings[0].document_id == doc_new.id

    db_findings = (
        await session.execute(
            select(Finding).where(
                Finding.task_id == task.id,
                Finding.source == "balance_check",
            )
        )
    ).scalars().all()
    assert len(db_findings) == 2
    doc_ids = {f.document_id for f in db_findings}
    assert doc_ids == {doc_old.id, doc_new.id}


@pytest.mark.asyncio
async def test_run_balance_check_dimension_findings_document_id_null(db_session):
    """维度 finding（source='rule'）的 document_id 为 NULL，余额校验不误删。

    回归：run_balance_check 的删除范围带 document_id 条件，不会扫到 document_id=NULL
    的维度 finding。
    """
    session, user = db_session
    task = Task(title="dim-coexist", status="completed", owner_id=user.id, config={})
    session.add(task)
    await session.flush()

    doc = Document(
        task_id=task.id, filename="d.xlsx", original_path="d.xlsx",
        status="completed", flow_tables={"records": []},
        portrait={
            "account_type": "bank_general",
            "column_mapping": ["transaction_time", "amount", "transaction_type", "balance"],
        },
    )
    session.add(doc)
    await session.flush()
    session.add_all(
        [
            Finding(
                task_id=task.id, type="大额", severity="high", description="dim",
                confidence=0.9, status="pending", source="rule",
            ),
            _std_row(task.id, doc.id, 1, "2026-06-01 10:00:00", "1000.00", "", ""),
            # 不符：expected=800, BN=700
            _std_row(task.id, doc.id, 2, "2026-06-01 11:00:00", "700.00", "200.00", "支出"),
        ]
    )
    await session.commit()

    from app.services.audit.balance_check import run_balance_check
    findings = await run_balance_check(session, task.id, doc.id)
    await session.commit()
    assert len(findings) == 1

    rule_findings = (
        await session.execute(
            select(Finding).where(Finding.task_id == task.id, Finding.source == "rule")
        )
    ).scalars().all()
    assert len(rule_findings) == 1
    assert rule_findings[0].document_id is None
