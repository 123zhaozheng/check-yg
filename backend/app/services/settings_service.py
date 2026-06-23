# -*- coding: utf-8 -*-
"""Runtime settings helpers.

DEFAULT_SETTINGS 既提供环境兜底值，也提供设置项元数据（type/label/description/
options），供 ``GET /api/settings/schema`` 渲染前端表单。type 取 string|number|
boolean|select；select 必带 options 列表。向后兼容：旧调用方只读 ``value`` /
``category``，新增元数据键不影响。
"""

from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Setting


DEFAULT_SETTINGS: Dict[str, Dict[str, Any]] = {
    # --- LLM ---
    "llm.base_url": {
        "value": settings.LLM_API_ENDPOINT,
        "category": "llm",
        "type": "string",
        "label": "LLM 服务地址",
        "description": "OpenAI 兼容端点，必须以 /v1 结尾。",
    },
    "llm.model_name": {
        "value": settings.LLM_MODEL_NAME,
        "category": "llm",
        "type": "string",
        "label": "LLM 模型名称",
        "description": "如 gpt-4o-mini、qwen-plus 等 OpenAI 兼容模型名。",
    },
    "llm.api_key": {
        "value": settings.LLM_API_KEY,
        "category": "llm",
        "type": "string",
        "label": "LLM API Key",
        "description": "调用 LLM 服务的密钥。",
    },
    "llm.timeout": {
        "value": str(settings.LLM_TIMEOUT),
        "category": "llm",
        "type": "number",
        "label": "LLM 超时（秒）",
        "description": "单次 LLM 调用的超时时间。",
    },
    "llm.temperature": {
        "value": "0.2",
        "category": "llm",
        "type": "number",
        "label": "LLM 采样温度",
        "description": "0.0-2.0，越低输出越确定。",
    },
    "llm.max_tokens": {
        "value": "16000",
        "category": "llm",
        "type": "number",
        "label": "LLM 最大输出 token",
        "description": "单次响应的最大 token 数（兜底：阶段未指派卡片时用；reasoning 模型建议≥4096）。",
    },
    # --- MinerU ---
    "mineru.mode": {
        "value": "local",
        "category": "mineru",
        "type": "select",
        "label": "MinerU 模式",
        "description": "local=本地服务，public=公共 agent。",
        "options": ["local", "public"],
    },
    "mineru.url": {
        "value": "http://localhost:8000",
        "category": "mineru",
        "type": "string",
        "label": "MinerU 本地服务地址",
        "description": "本地 MinerU 服务地址。",
    },
    "mineru.public_url": {
        "value": "https://mineru.net/api/v1/agent",
        "category": "mineru",
        "type": "string",
        "label": "MinerU 公共 agent 地址",
        "description": "公共 agent 模式下的服务地址。",
    },
    "mineru.public_api_key": {
        "value": "",
        "category": "mineru",
        "type": "string",
        "label": "MinerU 公共 agent API Key",
        "description": "公共 agent 模式下的鉴权密钥。",
    },
    "mineru.timeout": {
        "value": "300",
        "category": "mineru",
        "type": "number",
        "label": "MinerU 超时（秒）",
        "description": "PDF 解析超时时间。",
    },
    # --- 抽取并发（extraction） ---
    "extraction.mineru_concurrency": {
        "value": "1",
        "category": "extraction",
        "type": "number",
        "label": "MinerU 解析并发",
        "description": "stage1 文档解析并发数，public mineru 建议保持低值。",
    },
    "extraction.llm_concurrency": {
        "value": "2",
        "category": "extraction",
        "type": "number",
        "label": "大模型并发",
        "description": "stage2 标准化文档级并发数。",
    },
    # --- 审查参数（audit） ---
    "audit.fuzzy_threshold": {
        "value": "0.6",
        "category": "audit",
        "type": "number",
        "label": "默认模糊匹配阈值",
        "description": "0.0-1.0，客户名单模糊匹配的默认阈值。",
    },
    "audit.default_confidence_threshold": {
        "value": "0.7",
        "category": "audit",
        "type": "number",
        "label": "默认置信阈值",
        "description": "AI 分析异常发现的默认置信阈值。",
    },
    "audit.default_analysis_mode": {
        "value": "quick",
        "category": "audit",
        "type": "select",
        "label": "默认分析模式",
        "description": "新建分析时的默认模式。",
        "options": ["quick", "deep"],
    },
    "audit.default_cleaning_ruleset": {
        "value": "default",
        "category": "audit",
        "type": "string",
        "label": "默认清洗规则集",
        "description": "清洗标准化使用的默认规则集名称。",
    },
    # --- 渠道启用（channel） ---
    "channel.bank.enabled": {
        "value": "true",
        "category": "channel",
        "type": "boolean",
        "label": "银行渠道启用",
        "description": "是否启用银行渠道流水导入。",
    },
    "channel.payment.enabled": {
        "value": "true",
        "category": "channel",
        "type": "boolean",
        "label": "支付渠道启用",
        "description": "是否启用支付渠道流水导入。",
    },
    "channel.wealth.enabled": {
        "value": "false",
        "category": "channel",
        "type": "boolean",
        "label": "理财渠道启用",
        "description": "是否启用理财渠道流水导入。",
    },
    "channel.securities.enabled": {
        "value": "false",
        "category": "channel",
        "type": "boolean",
        "label": "证券渠道启用",
        "description": "是否启用证券渠道流水导入。",
    },
}


def setting_category(key: str) -> str:
    """Infer a setting category from its dotted key."""
    if "." not in key:
        return "general"
    return key.split(".", 1)[0]


async def load_runtime_settings(db: AsyncSession) -> Dict[str, str]:
    """Load effective runtime settings with environment-backed defaults."""
    values = {key: item["value"] for key, item in DEFAULT_SETTINGS.items()}
    result = await db.execute(select(Setting))
    for item in result.scalars().all():
        values[item.key] = item.value
    return values


def get_int_setting(values: Dict[str, str], key: str, default: int, minimum: int, maximum: int) -> int:
    """Read a bounded integer setting."""
    try:
        value = int(values.get(key, default))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


def settings_schema(saved_values: Dict[str, str]) -> list[dict[str, Any]]:
    """合成设置项元数据列表供 ``GET /api/settings/schema``.

    每项: {key, category, type, label, description, options?, value}.
    value 优先用 DB 已存值，否则用 DEFAULT_SETTINGS 兜底。向后兼容：旧
    ``list_settings`` / ``get_setting`` / ``put_setting`` 不受影响。
    """
    items: list[dict[str, Any]] = []
    for key, meta in DEFAULT_SETTINGS.items():
        entry: dict[str, Any] = {
            "key": key,
            "category": meta.get("category", setting_category(key)),
            "type": meta.get("type", "string"),
            "label": meta.get("label", key),
            "description": meta.get("description", ""),
            "value": saved_values.get(key, meta.get("value", "")),
        }
        options = meta.get("options")
        if options:
            entry["options"] = list(options)
        items.append(entry)
    return items
