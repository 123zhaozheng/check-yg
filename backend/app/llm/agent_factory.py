"""pydantic-ai agent 工厂 —— 模块级单例，按连接参数缓存。

落地严格遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)：
- ``OpenAIChatModel`` + ``OpenAIProvider(base_url, api_key)``，复用 settings 的
  ``llm.*`` 四项（``LLM_API_ENDPOINT`` / ``LLM_API_KEY`` / ``LLM_MODEL_NAME`` /
  ``LLM_TIMEOUT``）。
- ``base_url`` 必须以 ``/v1`` 结尾（Chat Completions 走 ``/v1/chat/completions``）。
- agent 模块级创建一次、跨请求复用（无状态、线程安全）；per-request 数据走
  ``deps=``。这里按 (base_url, api_key, model, timeout, max_tokens, thinking)
  缓存，runtime settings 变了会重建对应 agent。
- ``trust_env=False``：显式传 ``httpx.AsyncClient(trust_env=False)``，等价旧
  httpx 直连实现，避免内网/ollama 环境走系统代理。
- 三模块 ``max_tokens`` 不同（classifier/portrait 1500，normalizer 4000），
  per-agent 设 ``ModelSettings``。
- ``temperature=0.1`` 保留（与旧实现一致，缩小回归 diff）。
- ``thinking``（06-23-llm-model-card）：透传到 ``ModelSettings(thinking=...)``
  控 reasoning 预算（research §1.3：统一字段 → OpenAI ``reasoning_effort``）。
  ``None``/``'off'`` 时不传该字段——避免给非 reasoning 模型发
  ``reasoning_effort`` 报错（research §3）。
"""

from __future__ import annotations

import logging
import threading
from typing import Optional, Sequence

import httpx
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings

logger = logging.getLogger(__name__)

# (base_url, api_key, model, timeout, max_tokens, thinking, temperature,
#  output_type, instructions, deps_type) -> Agent. ``thinking`` 计入 key——
# reasoning（low/medium/high）与非 reasoning（off/None）拿到不同 agent 实例
# （reasoning 实例带 ``OpenAIModelProfile(supports_thinking=True)``）。
_agent_cache: dict[tuple, Agent] = {}
_lock = threading.Lock()

# thinking 档位（off 不传 reasoning_effort）。与 llm_model.THINKING_LEVELS 对齐。
_THINKING_LEVELS = ("off", "low", "medium", "high")


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
    thinking: Optional[str] = None,
    temperature: Optional[float] = None,
    retries: int = 3,
    deps_type: type | None = None,
    toolsets: Optional[Sequence] = None,
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
    # temperature：未传时保留旧默认 0.1（缩小回归 diff）；卡片/runtime 指定
    # 时用指定值（prd ② temperature 可配）。
    effective_temp = 0.1 if temperature is None else float(temperature)
    model_settings = ModelSettings(
        temperature=effective_temp, max_tokens=max_tokens, timeout=timeout
    )
    # thinking：off/None 不传 reasoning_effort（非 reasoning 模型会报错）。
    # 见 research §1.3 / §3。
    send_thinking = bool(thinking) and thinking != "off" and thinking in _THINKING_LEVELS
    if send_thinking:
        model_settings["thinking"] = thinking  # type: ignore[typeddict-unknown-key]
    # 关键：OpenAIChatModel 默认 profile ``supports_thinking=False``，会导致
    # ``Model.prepare_request`` 把 ``thinking`` 字段从 model_settings 里**剥离**且
    # 不塞进 ``ModelRequestParameters.thinking``，最终 ``_translate_thinking`` 返
    # OMIT → ``reasoning_effort`` 根本不发到端点（research §3）。给 reasoning 模型
    # 传 ``OpenAIModelProfile(supports_thinking=True)`` 才能让 ``thinking=low``
    # 真正映射成 ``reasoning_effort=low`` 发出去。非 reasoning（send_thinking=False）
    # 时不传 profile，保留默认行为（thinking 也不会在 model_settings 里，安全）。
    # 只设 supports_thinking，不动 openai_supports_reasoning（避免触发
    # ``_drop_sampling_params_for_reasoning`` 丢 temperature）。
    chat_model = OpenAIChatModel(
        model,
        provider=provider,
        profile=OpenAIModelProfile(supports_thinking=True) if send_thinking else None,
        settings=ModelSettings(timeout=timeout, max_tokens=max_tokens),
    )
    # deps_type 传类型（conventions.md），None 时 agent 无 deps（与旧三模块一致）。
    return Agent(
        chat_model,
        output_type=output_type,
        instructions=instructions,
        retries={"tools": retries, "output": retries},
        model_settings=model_settings,
        deps_type=deps_type,
        toolsets=list(toolsets) if toolsets else None,
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
    thinking: Optional[str] = None,
    temperature: Optional[float] = None,
    deps_type: type | None = None,
    toolsets: Optional[Sequence] = None,
) -> Agent:
    """按连接参数取/建缓存 agent。

    传入 ``None`` 的参数回退到 ``settings`` 默认值（与 extractor 的
    ``runtime_settings.get(...) or settings.*`` 行为一致）。

    ``deps_type`` 传类型（conventions.md：deps_type=AuditDeps 传类型，deps=
    传实例）；为 None 时 agent 无 deps（与旧三模块 classifier/normalizer/portrait
    一致）。``deps_type`` 计入缓存 key，不同 deps_type 得到不同 agent 实例。

    ``thinking`` 计入缓存 key（同 max_tokens）——不同 reasoning 预算得到不同
    agent 实例。``None``/``'off'`` 不传 ``reasoning_effort``（非 reasoning 模型
    会报错——research §3）。

    ``temperature`` 计入缓存 key；``None`` 时保留旧默认 0.1。

    ``toolsets``：附加 ``FunctionToolset``（conventions.md Toolset 用法），如
    AI 审查的只读工具集。**不计入缓存 key**——toolset 是可变容器（同 key 复用
    一个 agent 时，工具集已挂在该 agent 上，重复传同一 toolset 实例即可）。
    首次为某 key 建 agent 时挂上；后续同 key 命中缓存直接返回已挂工具集的 agent。
    调用方应传**同一个 toolset 实例**（模块级单例），避免每次重建。
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
        thinking or "off",
        None if temperature is None else float(temperature),
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
                thinking=thinking,
                temperature=temperature,
                deps_type=deps_type,
                toolsets=toolsets,
            )
            _agent_cache[key] = agent
        return agent
