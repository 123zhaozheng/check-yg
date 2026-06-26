# -*- coding: utf-8 -*-
"""维度提示词固定模板拼装（06-26-ai-agent, PRD §三）.

``build_dimension_prompt(name, purpose, steps, judgment, severity) -> str``：
按固定四段模板拼维度完整 prompt。系统预冻维度和追问 agent ``create_dimension``
沉淀的维度**共用一套模板**——维度 = 提示词，新维度沉淀零代码。

模板四段：
1. 维度标题段（含默认 severity）+ 任务段（含 ``purpose``）。
2. 可用工具说明段（**固定**，列 5 个只读工具）。
3. 分析步骤段（来自维度 ``steps`` 字段，格式化为 ``tool(params)`` 序列）。
4. 判定标准段（``judgment``）+ 输出 few-shot 样例段（**固定**，一条好 +
   一条零命中空输出）。

``purpose`` / ``steps`` / ``judgment`` 随维度变；工具说明段 + few-shot 段固定。
"""

from __future__ import annotations

import json
from typing import Any


# 固定段：可用工具说明（5 个只读工具，均带 limit 防爆 context）。
_TOOLS_SECTION = """## 可用工具（只读，已剔除无时分秒记录，均带limit防爆context）
- get_task_summary / query_by_time / query_by_amount /
  query_by_counterparty / query_burst
按需调用，想调几次调几次，查够再下结论。"""


# 固定段：输出 few-shot 样例（一条好 DimensionFinding + 一条零命中空输出）。
_FEW_SHOT_SECTION = """## 输出（few-shot 样例）
产出 DimensionFinding：type/severity/counterparty(可空)/amount(合计)/
detail_text(自然语言分析，引用真实笔数与样本)/evidence_record_ids/confidence。
零命中 → 空 findings，detail_text="未发现X异常"。

样例1（命中，好的输出）：
{"type":"夜间交易","severity":"high","counterparty":null,"amount":"¥120,000.00",
 "detail_text":"夜间时段(22:00-06:00)共命中 18 笔，合计 ¥120,000.00，占总交易笔数 23%。样本：2026-06-15 23:45 与对手方 X 发生 ¥30,000.00。",
 "evidence_record_ids":[101,105,108],"confidence":0.9}

样例2（零命中，空输出）：
{"findings":[],"detail_text":"未发现夜间交易异常"}"""


def _format_steps(steps: list[dict[str, Any]] | None) -> str:
    """把维度 steps 字段格式化为 ``tool(params)`` 序列文本。

    ``steps`` 形如 ``[{"tool": "query_by_time", "params": {"hours": [22,23,0]}}, ...]``。
    缺省 / 空返空串（步骤段留空，agent 自行决定）。
    """
    if not steps:
        return ""
    lines: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or "").strip()
        if not tool:
            continue
        params = step.get("params") or {}
        try:
            params_json = json.dumps(params, ensure_ascii=False)
        except (TypeError, ValueError):
            params_json = "{}"
        lines.append(f"- {tool}({params_json})")
    return "\n".join(lines) if lines else ""


def build_dimension_prompt(
    name: str,
    purpose: str,
    steps: list[dict[str, Any]] | None,
    judgment: str,
    severity: str,
) -> str:
    """按固定四段模板拼维度完整 prompt。

    Args:
        name: 维度名。
        purpose: 要查什么异常（1-2 句）。
        steps: 调用序列 ``list[{tool, params}]``。
        judgment: 命中 / severity 判定标准。
        severity: 默认 severity（high | medium | low）。

    Returns:
        拼好的完整 prompt 字符串（存 ``AuditDimension.prompt`` 列，跑分析时
        注入维度 agent 的 instructions）。
    """
    steps_text = _format_steps(steps)
    steps_section = (
        f"## 分析步骤\n{steps_text}" if steps_text else "## 分析步骤\n（按需自行调用工具）"
    )
    return (
        f"## 维度：{name}  （默认severity: {severity}）\n\n"
        f"## 任务\n"
        f"你是银行/支付流水审计助手，针对本任务 standard 流水检测以下异常。\n"
        f"{purpose}\n\n"
        f"{_TOOLS_SECTION}\n\n"
        f"{steps_section}\n\n"
        f"## 判定标准（决定是否产出finding及severity）\n"
        f"{judgment}\n"
        f"零命中则不产出，不要编造\n\n"
        f"{_FEW_SHOT_SECTION}"
    )
