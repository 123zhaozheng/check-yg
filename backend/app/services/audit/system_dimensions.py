# -*- coding: utf-8 -*-
"""预冻 5 个 system 维度定义（06-26-ai-agent, PRD §四）.

单源真相：5 个 system 维度的 ``name / purpose / steps / judgment / severity``
在此定义一次，``build_prompt()`` 用 ``build_dimension_prompt`` 拼好成品 prompt。
Alembic seed 迁移与运行时共享此定义，避免「迁移手写 prompt vs 运行时拼装」
两套机制漂移（code-reuse-thinking-guide：非对称机制产同输出陷阱）。

阈值规避 / 同日同额 / 快进快出 MVP 不预冻，留作沉淀示例或后续加。
"""

from __future__ import annotations

from typing import Any

from app.services.audit.dimension_prompt import build_dimension_prompt


# 5 个 system 维度定义（PRD §四）。steps.tool 限只读工具白名单。
SYSTEM_DIMENSIONS: list[dict[str, Any]] = [
    {
        "name": "夜间交易",
        "purpose": "检测非营业时段（22:00–次日06:00）的交易。",
        "steps": [
            {"tool": "query_by_time", "params": {"hours": [22, 23, 0, 1, 2, 3, 4, 5]}},
        ],
        "judgment": "命中即 high；若占任务总交易笔数 >20%，进一步上调 severity。",
        "severity": "high",
    },
    {
        "name": "大额交易",
        "purpose": "检测单笔大额交易（≥5万，现金监管口径）。",
        "steps": [
            {"tool": "query_by_amount", "params": {"mode": "large", "min": 50000}},
        ],
        "judgment": "单笔 ≥5万 high；命中笔数越多 severity 越高。",
        "severity": "high",
    },
    {
        "name": "整数金额",
        "purpose": "检测异常整数金额（尾随 ≥4 个 0）。",
        "steps": [
            {"tool": "query_by_amount", "params": {"mode": "round"}},
        ],
        "judgment": "集中出现 medium；偶发 low。",
        "severity": "medium",
    },
    {
        "name": "重复对手方",
        "purpose": "检测同一对手方高频往来（≥3 笔）。",
        "steps": [
            {"tool": "query_by_counterparty", "params": {"min_count": 3}},
        ],
        "judgment": "≥10 笔 high；3-9 笔 medium。",
        "severity": "medium",
    },
    {
        "name": "短间隔簇",
        "purpose": "检测同一对手方短时密集交易（≤30 分钟 ≥2 笔）。",
        "steps": [
            {"tool": "query_burst", "params": {"window_minutes": 30, "min_count": 2}},
        ],
        "judgment": "簇数 ≥3 high；否则按簇数升 severity。",
        "severity": "medium",
    },
]


def build_prompt(dim: dict[str, Any]) -> str:
    """拼单个维度的成品 prompt（复用 ``build_dimension_prompt``）。"""
    return build_dimension_prompt(
        name=dim["name"],
        purpose=dim["purpose"],
        steps=dim.get("steps"),
        judgment=dim["judgment"],
        severity=dim["severity"],
    )


def system_dimension_rows() -> list[dict[str, Any]]:
    """返回 5 个 system 维度的完整行（含拼好的 prompt），供 Alembic seed / 测试用。

    ``source=system``、``enabled=true``、``created_by=None``。
    """
    rows: list[dict[str, Any]] = []
    for dim in SYSTEM_DIMENSIONS:
        rows.append(
            {
                "name": dim["name"],
                "source": "system",
                "purpose": dim["purpose"],
                "steps": dim.get("steps"),
                "judgment": dim["judgment"],
                "severity": dim["severity"],
                "prompt": build_prompt(dim),
                "enabled": True,
                "created_by": None,
            }
        )
    return rows
