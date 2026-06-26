# -*- coding: utf-8 -*-
"""金额 / 时间多格式解析（06-26-ai-agent）.

从 legacy ``src/llm/audit_agent.py`` 搬 ``_parse_amount`` / ``_parse_datetime``
两个多格式解析函数到后端共享位，供 AI 审查只读工具复用——不在工具里重写
（code-reuse-thinking-guide：复用，不复制）。解析逻辑逐字保留，已由 legacy
验证覆盖多格式。

* ``parse_amount(value)`` —— 金额字符串 → float（剥千分位/货币符号/正号，取绝对值）。
* ``parse_datetime(value)`` —— 时间字符串 → ``datetime``（6 种常见格式 + ISO）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def parse_amount(amount_value: object) -> float:
    """金额字符串 → float（取绝对值，剥千分位/货币符号/正号）。

    对齐 legacy ``AuditAgent._parse_amount``：``None`` / 空 / 不可解析 → 0.0。
    """
    if amount_value is None:
        return 0.0
    amount_str = str(amount_value).strip()
    if not amount_str:
        return 0.0
    clean = (
        amount_str.replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("元", "")
        .replace("+", "")
    )
    try:
        return abs(float(clean))
    except (ValueError, TypeError):
        return 0.0


def parse_datetime(value: object) -> Optional[datetime]:
    """时间字符串 → ``datetime``（无时区）。

    对齐 legacy ``AuditAgent._parse_datetime``：``None`` / 空 / 不可解析 → None。
    候选格式 6 种 + ISO 8601 回退。
    """
    text = str(value or "").strip()
    if not text:
        return None

    candidates = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
