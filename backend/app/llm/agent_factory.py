"""pydantic-ai agent 工厂 —— 模块级单例，按连接参数缓存。

落地严格遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)：
- ``OpenAIChatModel`` + ``OpenAIProvider(base_url, api_key)``，复用 settings 的
  ``llm.*`` 四项（``LLM_API_ENDPOINT`` / ``LLM_API_KEY`` / ``LLM_MODEL_NAME`` /
  ``LLM_TIMEOUT``）。
- ``base_url`` 必须以 ``/v1`` 结尾（Chat Completions 走 ``/v1/chat/completions``）。
- agent 模块级创建一次、跨请求复用（无状态、线程安全）；per-request 数据走
  ``deps=``。这里按 (base_url, api_key, model, timeout, max_tokens) 缓存，
  runtime settings 变了会重建对应 agent。
- ``trust_env=False``：显式传 ``httpx.AsyncClient(trust_env=False)``，等价旧
  httpx 直连实现，避免内网/ollama 环境走系统代理。
- 三模块 ``max_tokens`` 不同（classifier/portrait 1500，normalizer 4000），
  per-agent 设 ``ModelSettings``。
- ``temperature=0.1`` 保留（与旧实现一致，缩小回归 diff）。
"""

from __future__ import annotations

import logging
import threading

import httpx
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings

logger = logging.getLogger(__name__)

# (base_url, api_key, model, timeout, max_tokens) -> Agent
_agent_cache: dict[tuple, Agent] = {}
_lock = threading.Lock()


def _normalize_base_url(base_url: str) -> str:
    """确保 base_url 以 ``/v1`` 结尾（Chat Completions 走 ``/v1/chat/completions``）。"""
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = url + "/v1"
    return url


def _build_agent(
    output_type: type,
    instructions: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: int,
    max_tokens: int,
    retries: int = 3,
    deps_type: type | None = None,
) -> Agent:
    """构造一个 pydantic-ai agent（模块级单例，按调用方参数缓存）。"""
    # AsyncOpenAI(max_retries=3) 处理瞬时 HTTP 429/5xx 重试，与旧 httpx 实现的
    # 应用层 3 次重试深度对齐（conventions.md 建议值）。output schema 校验失败
    # 的重试由 agent 的 ``retries={"output": N}`` 管，二者互补。
    # http_client 传 trust_env=False 的 AsyncClient，等价旧实现，避免内网/ollama
    # 环境走系统代理。
    from openai import AsyncOpenAI

    normalized_url = _normalize_base_url(base_url)
    provider = OpenAIProvider(
        openai_client=AsyncOpenAI(
            base_url=normalized_url,
            api_key=api_key,
            max_retries=3,
            timeout=timeout,
            http_client=httpx.AsyncClient(trust_env=False),
        ),
    )
    chat_model = OpenAIChatModel(
        model,
        provider=provider,
        settings=ModelSettings(timeout=timeout, max_tokens=max_tokens),
    )
    # deps_type 传类型（conventions.md），None 时 agent 无 deps（与旧三模块一致）。
    return Agent(
        chat_model,
        output_type=output_type,
        instructions=instructions,
        retries={"tools": retries, "output": retries},
        model_settings=ModelSettings(temperature=0.1, max_tokens=max_tokens, timeout=timeout),
        deps_type=deps_type,
    )


def get_agent(
    output_type: type,
    instructions: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
    max_tokens: int,
    deps_type: type | None = None,
) -> Agent:
    """按连接参数取/建缓存 agent。

    传入 ``None`` 的参数回退到 ``settings`` 默认值（与 extractor 的
    ``runtime_settings.get(...) or settings.*`` 行为一致）。

    ``deps_type`` 传类型（conventions.md：deps_type=AuditDeps 传类型，deps=
    传实例）；为 None 时 agent 无 deps（与旧三模块 classifier/normalizer/portrait
    一致）。``deps_type`` 计入缓存 key，不同 deps_type 得到不同 agent 实例。
    """
    base_url = base_url or settings.LLM_API_ENDPOINT
    api_key = api_key or settings.LLM_API_KEY
    model = model or settings.LLM_MODEL_NAME
    timeout = timeout or settings.LLM_TIMEOUT

    key = (
        _normalize_base_url(base_url),
        api_key,
        model,
        int(timeout),
        int(max_tokens),
        output_type,
        instructions,
        deps_type,
    )
    with _lock:
        agent = _agent_cache.get(key)
        if agent is None:
            agent = _build_agent(
                output_type,
                instructions,
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout=timeout,
                max_tokens=max_tokens,
                deps_type=deps_type,
            )
            _agent_cache[key] = agent
        return agent
