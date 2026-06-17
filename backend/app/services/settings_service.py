# -*- coding: utf-8 -*-
"""Runtime settings helpers."""

from __future__ import annotations

from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Setting


DEFAULT_SETTINGS: Dict[str, Dict[str, str]] = {
    "llm.base_url": {
        "value": settings.LLM_API_ENDPOINT,
        "category": "llm",
    },
    "llm.model_name": {
        "value": settings.LLM_MODEL_NAME,
        "category": "llm",
    },
    "llm.api_key": {
        "value": settings.LLM_API_KEY,
        "category": "llm",
    },
    "llm.timeout": {
        "value": str(settings.LLM_TIMEOUT),
        "category": "llm",
    },
    "mineru.mode": {
        "value": "local",
        "category": "mineru",
    },
    "mineru.url": {
        "value": "http://localhost:8000",
        "category": "mineru",
    },
    "mineru.public_url": {
        "value": "https://mineru.net/api/v1/agent",
        "category": "mineru",
    },
    "mineru.public_api_key": {
        "value": "",
        "category": "mineru",
    },
    "mineru.timeout": {
        "value": "300",
        "category": "mineru",
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
