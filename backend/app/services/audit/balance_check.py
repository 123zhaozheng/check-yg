# -*- coding: utf-8 -*-
"""余额防篡改校验（06-28-balance-column-check）.

确定性算术复核：**首尾锚点 + 时分秒 gate** 总额对账。流水**并发分批清洗**行序
不保证为原文档顺序（逐行链法不可靠）→ 改用按时分秒时序排，首尾两条余额当锚点，
``首条余额 + 后续净收支 = 期望末条余额``，对不上产 1 条文档级 finding——用来发现
员工篡改金额 / 删除流水行。OCR + 大模型清洗有不确定性，故不符行支持采纳/忽略
人工复核（复用 Finding 状态机）。无余额列 / 无时分秒行的文档跳过（默认通过）。

算法（PRD §四，纯逻辑函数 ``check_balance_totals`` + 异步 DB 写
``run_balance_check``）：
- gate：文档 ``column_mapping`` 含 ``"balance"``（有余额列）**且**有「时分秒」行
  （可按时序排）→ 跑校验；无时分秒 → 默认通过、跳过不报错。
- rows = 该文档 standard 行里：交易时间带时分秒（``_has_hms``）且 balance 非空，
  按 ``parse_datetime(transaction_time)`` 升序排。
- ``B1`` = ``parse_amount(rows[0].balance)``（首条锚点）；
  ``BN`` = ``parse_amount(rows[-1].balance)``（末条锚点）。
- ``net`` = Σ rows[1:] 带符号金额：收入 → +，支出 → −，其它 → 不计入（保守）。
- ``expected = B1 + net``；``tol = max(0.01, 0.0001 * abs(BN))``；
  ``abs(expected - BN) > tol`` → 产 1 条文档级不符 finding（detail_text 含
  首条/净收支/期望末条/实际末条/差额）。
- 容差 = 绝对 0.01 或 万分之一（大金额浮点/分级兜底）。

复用优先（code-reuse-thinking-guide）：Finding 状态机、parse_amount / parse_datetime
（``app/services/audit/parsing.py``）、时分秒判定（``_has_hms`` 判据对齐
``app/llm/analysis.py``）。不重复造。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Finding, FlowRecordRow
from app.services.audit.parsing import parse_amount, parse_datetime

logger = logging.getLogger(__name__)

#: Finding.source 值：余额校验产出的不符文档。与维度 finding（source='rule'）区分，
#: AI 分析页默认不显示、报告取 accepted。
SOURCE_BALANCE_CHECK = "balance_check"

#: parse_datetime 失败时的排序哨兵——排到最后（保留这些行，但不影响有序主体）。
_MAX_DATETIME = datetime.max


@dataclass
class BalanceTotalsRow:
    """总额对账中的一行（从 FlowRecordRow 投影）。

    纯数据载体，``check_balance_totals`` 只依赖这些字段，便于脱离 DB 单测纯逻辑。
    入参行应是「交易时间带时分秒且 balance 非空」的 standard 行（调用方过滤）。
    """

    id: int
    transaction_time: str
    balance: str
    amount: str
    transaction_type: str


@dataclass
class BalanceFinding:
    """余额校验产出的单条文档级不符（逻辑层产物，落库时映射成 Finding 行）。

    aggregate finding：文档级，无单行证据（evidence_record_ids 空）、无对手方。
    """

    amount: str
    detail_text: str


def _has_hms(tx_time: Optional[str]) -> bool:
    """交易时间是否带非零时分秒（剔「只记日期」/ 00:00:00 噪音）。

    判据对齐 ``app/llm/analysis.py::_has_hms``：``00:00:00`` 视为「只记日期」噪音
    （不可关）。带时分秒且非全 0 → True。跨模块同名小工具实现（PRD §四）。
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


def _row_has_balance_column(column_mapping: Any) -> bool:
    """portrait.column_mapping 是否含 ``"balance"``。

    column_mapping 是有序数组，元素为标准字段名字符串 / 字符串数组 / null。
    任一元素（或数组子元素）等于 ``"balance"`` 即视为该文档有余额列。
    """
    if not column_mapping:
        return False
    for entry in column_mapping:
        if entry == "balance":
            return True
        if isinstance(entry, list) and "balance" in entry:
            return True
    return False


def check_balance_totals(
    rows: List[BalanceTotalsRow],
) -> Optional[BalanceFinding]:
    """首尾锚点总额对账（纯逻辑，无 DB / 无 IO）。

    Args:
        rows: 该文档 standard 行里「交易时间带时分秒且 balance 非空」的行。
            函数内会按 ``parse_datetime(transaction_time)`` 升序重排（不依赖传入
            顺序——并发清洗行序不可靠）。

    Returns:
        不符则返回单条 ``BalanceFinding``（文档级，每文档最多一条）；相符或行不足
        返回 ``None``。

    算法见模块 docstring：首条余额 + 后续净收支 = 期望末条余额，容差内过、超容差产 finding。
    """
    if len(rows) < 2:
        return None

    # 按时分秒时序升序排（transaction_time 带 hms → parse_datetime 可靠）。
    # parse_datetime 失败返 None 的行排到最后（保留它们但不影响有序主体）。
    sorted_rows = sorted(rows, key=lambda r: parse_datetime(r.transaction_time) or _MAX_DATETIME)

    b1 = parse_amount(sorted_rows[0].balance)
    bn = parse_amount(sorted_rows[-1].balance)

    # 净收支：第 2 条起，收入 +、支出 −；transaction_type 非收/支不计入（保守）。
    net = 0.0
    for r in sorted_rows[1:]:
        amt = parse_amount(r.amount)
        if r.transaction_type == "收入":
            net += amt
        elif r.transaction_type == "支出":
            net -= amt
        # 其它方向 → 不计入（保守跳过）。

    expected = b1 + net
    tol = max(0.01, 0.0001 * abs(bn))

    if abs(expected - bn) <= tol:
        return None

    diff = bn - expected
    detail = (
        f"余额对账不符（按时序）：首条余额 {b1:,.2f} + 后续净收支 "
        f"{net:+,.2f} = 期望末条 {expected:,.2f}，实际末条 {bn:,.2f}，"
        f"差 {diff:+,.2f}。疑似金额被修改或流水被删/增。"
    )
    return BalanceFinding(amount=f"¥{abs(net):,.2f}", detail_text=detail)


async def run_balance_check(
    db: AsyncSession, task_id: int, document_id: int
) -> List[Finding]:
    """对一个文档跑余额校验并落库不符 Finding（首尾锚点总额对账）。

    触发条件（gate，PRD §四）：
    - 该文档 ``column_mapping`` 含 ``"balance"``（有余额列）→ 继续；否则返 []。
    - 筛「交易时间带时分秒（``_has_hms``）且 balance 非空」的 standard 行；
      筛后 < 2 行 → 返 []（无/不足时分秒数据 → 默认通过，不报错）。

    重跑策略（PRD §五）：先删该文档 ``source='balance_check'`` 的旧 finding 再重算。
    **删除范围按文档**（不是任务级）：多文档任务/append 下每个文档各自删自己的旧
    finding 重算，互不覆盖。靠 ``Finding.document_id`` 定位。

    Args:
        db: 异步 DB session（调用方负责 commit）。
        task_id: 任务 id。
        document_id: 文档 id。

    Returns:
        本次产出的 Finding 行列表（空表示无余额列、时分秒行不足、或全部平衡）。
    """
    # 取文档 portrait 判断有无余额列。
    from app.models import Document

    doc_result = await db.execute(
        select(Document.portrait).where(Document.id == document_id)
    )
    portrait = doc_result.scalar_one_or_none() or {}
    column_mapping = (portrait or {}).get("column_mapping")
    if not _row_has_balance_column(column_mapping):
        logger.debug(
            "余额校验跳过（无余额列）: task_id=%s document_id=%s", task_id, document_id
        )
        return []

    # 取该文档 standard 行（balance 非空），再筛交易时间带时分秒的。
    rows_result = await db.execute(
        select(FlowRecordRow)
        .where(
            FlowRecordRow.task_id == task_id,
            FlowRecordRow.document_id == document_id,
            FlowRecordRow.record_type == "standard",
            FlowRecordRow.balance.isnot(None),
            FlowRecordRow.balance != "",
        )
        .order_by(FlowRecordRow.row_index.asc())
    )
    db_rows = rows_result.scalars().all()

    # 时分秒 gate：只让带非零时分秒的行参与（才能可靠按时序排）。
    totals_rows = [
        BalanceTotalsRow(
            id=r.id,
            transaction_time=r.transaction_time or "",
            balance=r.balance or "",
            amount=r.amount or "",
            transaction_type=r.transaction_type or "",
        )
        for r in db_rows
        if _has_hms(r.transaction_time)
    ]

    finding_data = check_balance_totals(totals_rows)

    # 重跑：先删该文档 source='balance_check' 的旧 finding（行可能变了）。
    # 按文档范围删（document_id + task_id + source），不是任务级。
    await db.execute(
        delete(Finding).where(
            Finding.task_id == task_id,
            Finding.source == SOURCE_BALANCE_CHECK,
            Finding.document_id == document_id,
        )
    )

    if finding_data is None:
        logger.info(
            "余额校验完成（相符或不足）: task_id=%s document_id=%s",
            task_id,
            document_id,
        )
        return []

    # 文档级 aggregate finding：无单行证据、无对手方。
    finding = Finding(
        task_id=task_id,
        document_id=document_id,
        type="余额不符",
        severity="medium",
        description=finding_data.detail_text,
        counterparty=None,
        amount=finding_data.amount,
        confidence=1.0,
        status="pending",
        detail_text=finding_data.detail_text,
        evidence_record_ids=[],
        source=SOURCE_BALANCE_CHECK,
    )
    db.add(finding)

    logger.info(
        "余额校验完成: task_id=%s document_id=%s 产 1 条不符 finding",
        task_id,
        document_id,
    )
    return [finding]
