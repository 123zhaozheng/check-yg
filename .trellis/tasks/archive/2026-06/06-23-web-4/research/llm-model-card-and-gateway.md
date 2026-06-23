# Research: LLM 配置可配化 + 模型卡片（pydantic-ai 1.107.0 / OpenAI 兼容端点）

- **Query**: 把硬编码 max_tokens(1500/4000) 提升为设置页可配 + 模型卡片（上下文长度/最大输出/工具调用/推理模式/流式）；弄清 pydantic-ai ModelSettings 能配什么、是否有内置模型库、reasoning 模型如何控预算、max_tokens 能否映射成旧版、各家模型卡片默认值。
- **Scope**: mixed（内部源码 + 官方文档 web fetch）
- **Date**: 2026-06-23
- **pydantic-ai 版本**: **1.107.0**（backend venv 实测；全局 python 是 1.93.0，以 venv 为准）

> 关键结论先行（详细见各节）：
> 1. pydantic-ai **没有内置“模型卡片数据库”**（无上下文长度/最大输出/工具支持数值表）。它只有 `KnownModelName`（纯字符串枚举）+ `ModelProfile`（**能力开关**布尔标志，如 `openai_supports_tool_choice_required`，**不含数值**）。`context_window`/`max_output` 数值是 2026-05 才在 issue #4538/PR #4611 里提的新特性，**1.107.0 没有**。→ **模型卡片数值必须我们自己维护**。
> 2. `ModelSettings` 通用字段清单完整可用：`max_tokens / temperature / top_p / top_k / timeout / parallel_tool_calls / tool_choice / seed / presence_penalty / frequency_penalty / logit_bias / stop_sequences / extra_headers / thinking / service_tier / extra_body`。**reasoning 预算用统一字段 `thinking`**（`True/False/'minimal'/'low'/'medium'/'high'/'xhigh'`），OpenAI 路径映射成 `reasoning_effort`。OpenAI 专属还有 `openai_reasoning_effort`。
> 3. **`max_tokens` 在 OpenAIChatModel 路径被硬映射成 `max_completion_tokens`**（源码 `openai.py:1015`），**无法**直接发旧版 `max_tokens`。绕过办法：`ModelSettings(extra_body={"max_tokens": N})`（`openai.py:1035` 会透传 `extra_body`）。**但端点若两个都收会冲突**，需实测。
> 4. reasoning token **计入** `max_completion_tokens` 预算 + 上下文窗口，按 output token 计费。这直接解释了 step-3.7-flash 在 `max_completion_tokens=1500` 时“推理阶段烧光预算、没轮到 tool_call、pydantic-ai 抛 `UnexpectedModelBehavior: Model token limit exceeded before any response was generated`”。
> 5. **DashScope（Qwen 官方）`tool_choice` 只支持 `'auto'` / `'none'`，不支持 `'required'`**。modelscope 的 Qwen3.5-35B-A3B 在 `tool_choice:"required"` 下返回空壳 `choices:null` 与此同源。pydantic-ai 对 `output_type=pydantic模型` 默认硬走 `tool_choice:"required"`，是兼容性主因之一。

---

## 一、pydantic-ai 1.107.0 的 ModelSettings 能配哪些字段

### 1.1 通用 `ModelSettings`（`pydantic_ai/settings.py`，跨 provider）

`class ModelSettings(TypedDict, total=False)` —— 全部 optional，按 provider 透传。1.107.0 实测字段清单（源码 `backend/.venv/.../pydantic_ai/settings.py:81-347`，与官方文档 https://ai.pydantic.dev/api/settings/ 一致）：

| 字段 | 类型 | 含义 | OpenAI 兼容端点映射 |
|---|---|---|---|
| `max_tokens` | `int` | 生成停止前的最大 token 数 | **→ `max_completion_tokens`**（见 §4） |
| `temperature` | `float` | 随机性，0=分析/多选，高=创意 | `temperature` |
| `top_p` | `float` | 核采样（与 temperature 二选一） | `top_p` |
| `top_k` | `int` | 只从 top K 采样（Gemini/Anthropic/Cohere 用，OpenAI **不传**） | OpenAI 不支持 |
| `timeout` | `float \| Timeout` | 单请求超时秒数（覆盖 client 级） | `timeout` |
| `parallel_tool_calls` | `bool` | 是否允许并行 tool 调用（o1 不支持） | `parallel_tool_calls` |
| `tool_choice` | `ToolChoice` | `'auto'/'none'/'required'/list[str]/ToolOrOutput/None` | `tool_choice`（见 §4.3） |
| `seed` | `int` | 随机种子 | `seed` |
| `presence_penalty` | `float` | 新 token 是否已出现过的惩罚 | `presence_penalty` |
| `frequency_penalty` | `float` | 按 token 频率的惩罚 | `frequency_penalty` |
| `logit_bias` | `dict[str,int]` | 改变指定 token 出现概率 | `logit_bias` |
| `stop_sequences` | `list[str]` | 停止序列 | `stop` |
| `extra_headers` | `dict[str,str]` | 额外请求头 | `extra_headers` |
| `thinking` | `ThinkingLevel` | **统一推理开关**：`True/False/'minimal'/'low'/'medium'/'high'/'xhigh'` | OpenAI → `reasoning_effort`（见 §3） |
| `service_tier` | `ServiceTier` | `'auto'/'default'/'flex'/'priority'` | `service_tier` |
| `extra_body` | `object` | **额外请求体字段注入**（关键逃生口） | `extra_body` |

> 注意：`ModelSettings` 里**没有** `max_completion_tokens` 这个键——你永远写 `max_tokens`，pydantic-ai 内部决定发成 `max_completion_tokens` 还是 `max_tokens`（OpenAI 路径=前者，见 §4.1）。也**没有** `reasoning_effort` 这个通用键——通用层叫 `thinking`，OpenAI 专属叫 `openai_reasoning_effort`。

### 1.2 OpenAI 专属 `OpenAIChatModelSettings`（`pydantic_ai/models/openai.py:501`）

继承 `ModelSettings`，额外字段（`openai_` 前缀，可跨 provider 合并）：

| 字段 | 含义 |
|---|---|
| `openai_reasoning_effort` | OpenAI 原生 reasoning effort（`ReasoningEffort`：low/medium/high/…，优先级高于统一 `thinking`） |
| `openai_logprobs` / `openai_top_logprobs` | logprob |
| `openai_store` | 是否存储响应（Responses API） |
| `openai_user` | 终端用户 id |
| `openai_service_tier` | OpenAI 专属 service tier（优先级高于统一 `service_tier`） |
| `openai_prediction` | predicted outputs |
| `openai_prompt_cache_key` / `openai_prompt_cache_retention` | prompt 缓存控制 |
| `openai_continuous_usage_stats` | 流式累计 usage |

`OpenAIResponsesModelSettings`（Responses API，`openai.py:582`）还多 `openai_native_tools / openai_reasoning_summary / openai_send_reasoning_ids / openai_truncation / openai_text_verbosity`。我们用的是 `OpenAIChatModel`（Chat Completions），用不到这些。

### 1.3 reasoning 相关参数总结（用户重点问的）

- **统一字段 `thinking`**：`ModelSettings(thinking='low')` 或 `Thinking` capability（`pydantic.dev/docs/ai/advanced-features/thinking/`）。OpenAI 路径经 `_translate_thinking` 映射成 `reasoning_effort`：`True→'medium'`、`'low'→'low'`、`'high'→'high'`、`'xhigh'→'xhigh'`、`False→'none'`（`profiles/openai.py:29-37` 的 `OPENAI_REASONING_EFFORT_MAP`）。
- **OpenAI 专属 `openai_reasoning_effort`**：直接控 `reasoning_effort`，优先级高于 `thinking`。
- **没有 `max_completion_tokens` 字段、没有 `reasoning`/`thinking_budget` 通用字段**：要传 DeepSeek V4 那种 `extra_body={"thinking":{"type":"enabled"}}`，只能走 `extra_body`。
- reasoning 启用时，`temperature/top_p/presence_penalty/frequency_penalty/logit_bias/openai_logprobs/openai_top_logprobs` 这 7 个采样参数会被 `_drop_sampling_params_for_reasoning`（`openai.py:439-466`）丢弃（GPT-5.1+ 且 `reasoning_effort='none'` 时除外）。

来源：
- 源码 `backend/.venv/Lib/site-packages/pydantic_ai/settings.py:81-359`
- 源码 `backend/.venv/Lib/site-packages/pydantic_ai/models/openai.py:501-634`、`1015`、`1019`、`1035`、`439-466`
- 源码 `backend/.venv/Lib/site-packages/pydantic_ai/profiles/openai.py:29-37`
- 官方文档 https://ai.pydantic.dev/api/settings/
- 官方文档 https://ai.pydantic.dev/api/models/openai/
- Thinking 指南 https://pydantic.dev/docs/ai/advanced-features/thinking/

---

## 二、pydantic-ai 是否提供“模型卡片”/内置模型数据库

**结论：没有内置数值型模型卡片。需要自己维护。**

pydantic-ai 与“模型”相关的内置设施有三层，**都不含上下文长度/最大输出数值**：

1. **`KnownModelName`**（`pydantic_ai/models/_known_model_names.py`）—— 只是一个 `Literal[...]` 字符串枚举（如 `'openai:gpt-5.2'`、`'deepseek:deepseek-reasoner'`、`'moonshotai:kimi-latest'`、`'groq:qwen/qwen-3-32b'`、`'huggingface:Qwen/Qwen3.5-35B-A3B'` 等）。**纯名字**，无任何元信息。用途仅是类型提示 + `Agent('openai:gpt-5.2')` 简写自动选 model/provider/profile。

2. **`ModelProfile`**（`pydantic_ai/profiles/__init__.py`）—— **能力开关（布尔标志）**，不是数值。字段如：
   - `supports_tools` / `supports_json_schema_output` / `supports_json_object_output`
   - `supports_thinking` / `thinking_always_enabled`（reasoning 模型=True）
   - `thinking_tags`（默认 `('<think>','</think>')`）
   - OpenAI 专属（`profiles/openai.py`）：`openai_supports_tool_choice_required`（**关键**：MoonshotAI/Qwen3-coder 等设 False 时，`tool_choice:'required'` 会被降级成 `'auto'`，见 §4.3）、`openai_supports_strict_tool_definition`、`openai_supports_reasoning`、`openai_chat_thinking_field`（DeepSeek/Moonshot 用 `reasoning_content`，Ollama/vLLM 用 `reasoning`，见 `openai.py:1147-1173`）。
   - 各家 profile 函数：`profiles/deepseek.py`（R1=`thinking_always_enabled`，V4=`supports_thinking`）、`profiles/qwen.py`（qwen-3-coder=`openai_supports_tool_choice_required=False`）、`profiles/moonshotai.py`（只设 `ignore_streamed_leading_whitespace`，**没**关 `tool_choice_required`——与 OpenAIModelProfile docstring 说“MoonshotAI 不接受 required”有出入，见 §4.3 caveat）。

3. **`context_window` / `max_output` 数值** —— **1.107.0 没有**。这是 2026-03 才提的 feature request（issue #4538 “Expose context window size on ModelProfile and usage limits/tokens on RunContext”，PR #4611，milestone 2026-05）。我们装的 1.107.0 早于该特性落地，`ModelProfile` 里查不到这两个字段（已 grep 确认 `context_window/max_output_tokens` 在整个包内 0 命中）。

> “Pydantic AI Gateway”（`ai.pydantic.dev/gateway/`）是 Pydantic 自家的多 provider 统一网关（logfire 托管、`gateway/` 前缀模型名），**不是模型元信息数据库**，且我们是自建 OpenAI 兼容端点，用不到。

**落地含义**：设置页的“模型卡片”（上下文长度 / 最大输出 / 是否支持 tool_choice:required / 是否 reasoning 模型 / 是否支持流式）**必须我们自己维护一张表**（见 §5）。pydantic-ai 能帮我们的只是：按模型名选 profile 自动降级 `tool_choice`、自动识别 `reasoning_content` 字段——这些是“能力开关”，不是“数值限制”。

来源：
- 源码 `backend/.venv/Lib/site-packages/pydantic_ai/models/_known_model_names.py`（全文，纯 Literal）
- 源码 `backend/.venv/Lib/site-packages/pydantic_ai/profiles/__init__.py:41-180`
- 源码 `backend/.venv/Lib/site-packages/pydantic_ai/profiles/openai.py:58-251`、`profiles/deepseek.py`、`profiles/qwen.py`、`profiles/moonshotai.py`
- 官方文档 https://pydantic.dev/docs/ai/api/pydantic-ai/profiles/
- 官方文档 https://ai.pydantic.dev/models/ （Overview：Model/Provider/Profile 三层定义）
- 官方文档 https://ai.pydantic.dev/gateway/ （Gateway 是托管网关，非模型库）
- GitHub issue #4538 https://github.com/pydantic/pydantic-ai/issues/4538 （context_window on ModelProfile 是新 feature，2026-05 milestone）

---

## 三、OpenAI 兼容端点的 reasoning 模型如何控制推理预算

### 3.1 OpenAI Chat Completions 原生参数

OpenAI Chat Completions API 用 **`reasoning_effort`**（不是 `reasoning`）控制推理预算，值 `none/minimal/low/medium/high/xhigh`（各模型支持的子集不同，GPT-5.5 默认 `medium`）。Responses API 用 `reasoning.effort`。**reasoning token 计入 `max_completion_tokens` 预算 + 上下文窗口，按 output token 计费**——这是官方明确写的：

> “While reasoning tokens are not visible via the API, they still occupy space in the model's context window and are billed as output tokens.”

pydantic-ai 在 Chat Completions 路径把 `thinking`/`openai_reasoning_effort` 映射成请求体的 `reasoning_effort`（`openai.py:1019`）。

### 3.2 stepfun step-3.7-flash

- 256K 上下文，198B 总参/11B 激活 MoE，多模态（图/视频）。
- **`reasoning_effort` 三档**：`low`（简单问答/摘要）、`medium`（默认，通用推理）、`high`（复杂数学/规划/代码）。Chat Completions API 用 `reasoning_effort`，Messages API 用 `output_config.effort`。
- **支持 `tools`/`tool_choice`**（官方明说 reliable tool_choice orchestration）——所以 step-3.7-flash **本身支持 tool calling**，不是 tool_choice 不兼容的问题。
- 官方模型页/Quickstart **未明说**“reasoning token 是否计入 max_tokens/max_completion_tokens”，但按 OpenAI 兼容语义 + 我们实测现象（见下），**reasoning token 计入 `max_completion_tokens`**。
- **没有“关 reasoning”的开关**：只有 low/medium/high 三档，最低 `low`（不是 none）。即无法完全关闭推理，只能降到 low。
- 推理走 `reasoning_content` 字段（与 DeepSeek 同），pydantic-ai 的 `openai_chat_thinking_field='reasoning_content'` profile 能识别（`openai.py:1147-1173` 默认就检查 `reasoning`/`reasoning_content`）。

### 3.3 我们实测现象的根因（step-3.7-flash + max_completion_tokens=1500）

`UnexpectedModelBehavior: Model token limit exceeded before any response was generated` 的成因链：
1. pydantic-ai 把 `ModelSettings(max_tokens=1500)` 映射成 `max_completion_tokens=1500`（§4.1）。
2. step-3.7-flash 默认 `reasoning_effort=medium`，先跑 CoT 推理。
3. **reasoning token 计入 `max_completion_tokens`**，1500 预算在推理阶段就被烧光。
4. 模型还没轮到输出 `tool_call`（结构化输出的唯一出口）就触发 token 上限，返回空/截断。
5. pydantic-ai 拿不到 tool_call → 抛 `UnexpectedModelBehavior`。

**修复方向（供 implement 任务决策）**：
- **(a) 调大 max_completion_tokens**：reasoning 模型建议至少 4096~8192（low effort）或更高。这是“设置页可配 max_tokens”的核心动机——硬编码 1500 对 reasoning 模型根本不够。
- **(b) 降 reasoning effort 到 `low`**：`ModelSettings(thinking='low')` 或 `openai_reasoning_effort='low'`，减少推理 token 消耗。
- **(c) 换非 reasoning 模型**做分类/画像/标准化（这类任务不需要深度推理，普通 chat 模型 + tool 即可）。
- (a)+(b) 组合最稳：大预算 + 低推理。

### 3.4 DeepSeek-R1 / DeepSeek-reasoner

- **`deepseek-reasoner`（R1）**：`max_tokens` 默认 32K、最大 64K（**含 CoT**），输出 `reasoning_content`（CoT）+ `content`（答案）。**不支持 Function Calling**，不支持 `temperature/top_p/presence_penalty/frequency_penalty/logprobs`（设了不报错但无效）。多轮要把上一轮 `reasoning_content` 删掉再传，否则 400。
- **`deepseek-chat`（V3，非 thinking）**：支持 function calling（社区反映“仍不太稳”）。
- **新版 `deepseek-v4-flash` / `deepseek-v4-pro`**（2026）：上下文 **1M**，最大输出 **384K**，支持 thinking + non-thinking 双模式（默认 thinking 开），**支持 tool calls（含 thinking 模式）**。控制参数（OpenAI 格式）：`reasoning_effort`（`high`/`max`，`low`/`medium`→`high`、`xhigh`→`max`）+ `extra_body={"thinking":{"type":"enabled"/"disabled"}}`。`deepseek-chat`/`deepseek-reasoner` 2026/07/24 弃用，分别对应 v4-flash 的 non-thinking/thinking 模式。
- **对 pydantic-ai 的含义**：用 DeepSeek V4 thinking 时，`extra_body={"thinking":{"type":"enabled"}}` 必须我们自己传（pydantic-ai 的 `thinking` 字段只映射 `reasoning_effort`，不会生成 DeepSeek 私有的 `thinking` body）。reasoning_content 字段 pydantic-ai 能自动识别。

### 3.5 Qwen3 系列

- 开源 Qwen3 / Qwen3.5 / Qwen3.6 支持 **thinking + non-thinking 双模式**（单模型内切换）。DashScope deep thinking 用 `extra_body={"enable_thinking": True}` 之类（hybrid thinking 默认开）。`reasoning_effort` 在 DashScope Responses API 支持。
- **DashScope `tool_choice` 只支持 `'auto'` / `'none'`，不支持 `'required'`**（官方 function calling 文档原话）——这是 modelscope Qwen3.5 返回空壳的同源限制。
- pydantic-ai `profiles/qwen.py` 对 `qwen-3-coder` 显式设 `openai_supports_tool_choice_required=False`（会自动把 `required` 降级 `auto`），但对 `qwen3.5` 只设了 json schema 支持，**没**关 tool_choice_required → 走 modelscope 时仍发 `required` → 空壳。

来源：
- OpenAI reasoning 指南 https://developers.openai.com/api/docs/guides/reasoning （reasoning_effort 值、reasoning token 占上下文+按 output 计费）
- stepfun 模型页 https://platform.stepfun.ai/docs/en/guides/models/step-3.7-flash （256K、reasoning_effort low/medium/high、tool_choice 支持）
- stepfun HuggingFace https://huggingface.co/stepfun-ai/Step-3.7-Flash （256k context、三档 reasoning）
- DeepSeek reasoner 文档 https://api-docs.deepseek.com/guides/reasoning_model （max_tokens 默认 32K max 64K 含 CoT、不支持 function calling）
- DeepSeek V4 thinking mode https://api-docs.deepseek.com/guides/thinking_mode （reasoning_effort high/max、extra_body thinking、tool calls in thinking）
- DeepSeek V4 pricing/model https://api-docs.deepseek.com/quick_start/pricing （context 1M、max output 384K、deepseek-chat/reasoner 2026/07/24 弃用）
- DeepSeek tool calls https://api-docs.deepseek.com/guides/tool_calls （strict mode、thinking 模式 tool use）
- DashScope function calling https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling （tool_choice 仅 auto/none）
- DashScope deep thinking https://www.alibabacloud.com/help/en/model-studio/deep-thinking （hybrid thinking 默认开）
- 源码 `openai.py:1147-1173`（reasoning_content 字段自动识别）

---

## 四、max_tokens 能否映射成旧版 max_tokens / 能否传额外 body

### 4.1 `max_tokens` → `max_completion_tokens` 是硬编码

`OpenAIChatModel._chat_completions_create`（`openai.py:1006-1036`）调 `self.client.chat.completions.create(...)` 时：

```python
max_completion_tokens=model_settings.get('max_tokens', OMIT),  # 第 1015 行
```

即 `ModelSettings` 里的 `max_tokens` **无条件**映射成 OpenAI 新参数 `max_completion_tokens`，**没有**开关让它发旧版 `max_tokens`。社区 issue #1559（2025-04）“max_completion_tokens is not a valid openAI argument”至今仍是 `need confirmation` 状态，pydantic-ai **未**加回旧 `max_tokens` 选项——因为对真 OpenAI 而言 `max_completion_tokens` 才是正确参数名（o1 起旧 `max_tokens` 已 deprecated/不兼容）。

### 4.2 `extra_body` 是官方逃生口

同一段代码第 1035 行：

```python
extra_body=model_settings.get('extra_body'),
```

`ModelSettings` 有 `extra_body: object` 字段（`settings.py:338-347`，OpenAI/Anthropic/Groq/Outlines 支持）。**任何端点私有的请求体字段都能从这里透传**。所以：
- 想发旧版 `max_tokens`：`ModelSettings(max_tokens=OMIT, extra_body={"max_tokens": N})`——但 `max_tokens` 是必填式 optional，不传就 OMIT，可只靠 `extra_body` 注入。**注意**：若端点同时收 `max_completion_tokens` 和 `extra_body.max_tokens` 会冲突；对只认旧 `max_tokens` 的端点（如部分老 vLLM/Ollama 部署），此法可行；对 modelscope 这种认 `max_completion_tokens` 的，改旧名无意义。
- DeepSeek V4 的 `extra_body={"thinking":{"type":"enabled"}}`、DashScope 的 `extra_body={"enable_thinking": True}` 都走这条。

### 4.3 `tool_choice:"required"` 能否关掉（顺带，因为这跟 max_tokens 一起是兼容性主因）

pydantic-ai 对 `output_type=<PydanticModel>` 的 agent，结构化输出走 tool-calling：注册一个 function tool + `tool_choice="required"` 强制调用。能否发 `required` 由 profile 的 `openai_supports_tool_choice_required` 决定（`openai.py:4194-4210` `_support_tool_forcing`）：
- **True**（OpenAI、modelscope Qwen3.5 默认）：发 `tool_choice:"required"` → modelscope 返回空壳 `choices:null`。
- **False**（`qwen-3-coder` profile）：自动降级成 `'auto'`（静默，不报错）——除非用户**显式**在 `ModelSettings` 里设 `tool_choice='required'`，那会抛 `UserError`。

> **caveat**：`profiles/moonshotai.py` 只设了 `ignore_streamed_leading_whitespace`，**没有**把 `openai_supports_tool_choice_required` 设成 False，但 `profiles/openai.py:100-105` 的 docstring 明说“MoonshotAI currently does not accept `tool_choice='required'`”。即 Moonshot/Kimi 走 `OpenAIChatModel` 时 pydantic-ai **仍会发 `required`**，可能踩坑。若上 Kimi，需自己传 `OpenAIModelProfile(openai_supports_tool_choice_required=False)` 或显式 `ModelSettings(tool_choice='auto')` 覆盖。

来源：
- 源码 `openai.py:1006-1036`（`max_completion_tokens` 硬映射、`extra_body` 透传）
- 源码 `settings.py:338-347`（`extra_body` 字段定义）
- 源码 `openai.py:4194-4210`（`_support_tool_forcing`：tool_choice required 降级逻辑）
- 源码 `openai.py:1231-1258`（`_get_tool_choice`：required→auto 降级）
- 源码 `profiles/openai.py:100-105`（MoonshotAI 不接受 required 的 docstring）
- 源码 `profiles/qwen.py:13-19`（qwen-3-coder 设 False）
- 源码 `profiles/moonshotai.py`（未设 False）
- GitHub issue #1559 https://github.com/pydantic/pydantic-ai/issues/1559

---

## 五、常见 reasoning / 兼容模型卡片默认值（供设置页）

> 数值来自各家官方文档/模型卡。**“最大输出”对 reasoning 模型含 reasoning token**，所以 pydantic-ai 里的 `max_tokens`（→`max_completion_tokens`）必须为 reasoning 预留余量。`tool_choice:required` 列 = 端点是否接受 OpenAI `tool_choice:"required"`（pydantic-ai 结构化输出需要）。

| 模型 | 上下文长度 | 最大输出 | 支持 function calling | `tool_choice:"required"` | reasoning 模型 | 备注 |
|---|---|---|---|---|---|---|
| **stepfun step-3.7-flash** | 256K | 官方未公布单值（reasoning 计入 max_completion_tokens） | 是 | **是**（官方支持 tools/tool_choice） | 是（reasoning_effort low/medium/high，无 none） | 198B/11B MoE，多模态。我们实测 1500 预算被 reasoning 烧光 |
| **deepseek-chat**（V3/V4 non-thinking） | 1M（V4） | 384K（V4 最大） | 是（V4 含 thinking 模式） | 是 | 否（non-thinking） | `deepseek-chat` 2026/07/24 弃用→v4-flash non-thinking |
| **deepseek-reasoner**（R1） | 128K（R1 经典） | max_tokens 默认 32K、最大 64K（含 CoT） | **否**（R1 不支持 function calling） | 否（无 FC 即无 tool_choice） | 是（always thinking） | R1 不能做 pydantic-ai 结构化输出（要 function calling） |
| **deepseek-v4-pro** | 1M | 384K | 是（含 thinking 模式） | 是 | 是（thinking on/off 可切，reasoning_effort high/max） | 需 `extra_body={"thinking":{"type":"enabled"}}` |
| **qwen-plus / qwen-max**（DashScope） | 1M（Qwen3.5-Flash=1M；qwen3.7-max 文档 Context 1M / Max Output 65.53K） | qwen3.7-max ~65K | 是 | **仅 auto/none，不支持 required** | Qwen3+ 支持 thinking/non-thinking 切换 | DashScope `tool_choice` 只 auto/none；需 `extra_body` 控 thinking |
| **Qwen3.5-35B-A3B**（modelscope/开源） | 262,144 原生，可扩到 1,010,000 | 开源卡未单列最大输出 | 是 | **modelscope 端实测不支持（返回空壳）** | 是（hybrid thinking 默认开） | 我们当前用的模型；hosted 版=Qwen3.5-Flash(1M) |
| **kimi k2.6**（Moonshot） | 256K（262,144） | 官方未公布单值（Cloudflare 卡未列 max output） | 是（多轮 tool calling、structured outputs） | **未明说支持 required**（pydantic-ai profile 默认 True 但 docstring 警告 Moonshot 不接受） | 是（thinking + instant 模式） | OpenAI 兼容 base_url `api.moonshot.ai/v1`；上 Kimi 建议显式 `tool_choice='auto'` 或 profile 关 required |
| kimi-2.7（用户提及 256K/32K） | 256K | 32K（用户提供，**未能从官方文档独立核实**，K2.6 官方未列 32K 上限） | 是 | 待核实 | 是 | 见 caveat |

**给设置页的默认 max_tokens 建议**（reasoning 模型要给推理留余量）：
- 非 reasoning chat 模型（deepseek-chat non-thinking、qwen-plus non-thinking、kimi instant）：classifier 1500~2000、normalizer 4000~6000 可接受。
- reasoning 模型（step-3.7-flash、deepseek-reasoner/v4-pro thinking、qwen thinking、kimi thinking）：**至少 4096 起步**，复杂任务（normalizer 标准化长流水）建议 8192~16384，并配合 `thinking='low'` 降推理消耗。1500 对 reasoning 模型必失败。

来源（§5）：
- step-3.7-flash：https://platform.stepfun.ai/docs/en/guides/models/step-3.7-flash 、https://huggingface.co/stepfun-ai/Step-3.7-Flash
- DeepSeek：https://api-docs.deepseek.com/quick_start/pricing 、https://api-docs.deepseek.com/guides/reasoning_model 、https://api-docs.deepseek.com/guides/thinking_mode
- Qwen3.5-35B-A3B：https://huggingface.co/Qwen/Qwen3.5-35B-A3B （Context 262,144 natively, extensible up to 1,010,000）
- Qwen3.7-Max：https://www.qwencloud.com/models/qwen3.7-max （Context 1M, Max Input 991.80K, Max Output 65.53K）
- DashScope tool_choice：https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling
- Kimi K2.6：https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart 、https://developers.cloudflare.com/ai/models/@cf/moonshotai/kimi-k2.6/ （262,144 context, function calling Yes, reasoning Yes）

---

## 六、落地到设置页 + 模型卡片：pydantic-ai 给什么、我们维护什么

### 6.1 pydantic-ai 已经给我们的（不用自己造）
- `ModelSettings` 通用字段透传（§1.1）：设置页配 `max_tokens / temperature / top_p / timeout / presence_penalty / frequency_penalty / thinking / tool_choice` 都能直接落到请求体。
- `extra_body` 逃生口（§4.2）：DeepSeek `thinking` body、DashScope `enable_thinking`、端点私有参数都能透传。
- `thinking` 统一字段 → OpenAI `reasoning_effort` 自动映射（§1.3）。
- profile 自动降级 `tool_choice:"required"`→`"auto"`（仅当 `openai_supports_tool_choice_required=False`，如 qwen-3-coder；modelscope Qwen3.5 / Moonshot **没**自动降级，需手动处理，见 §4.3 caveat）。
- `reasoning_content` 字段自动识别（DeepSeek/Moonshot/stepfun 的 CoT 不会丢）。

### 6.2 我们必须自己维护的
- **模型卡片数值表**（§5）：上下文长度 / 最大输出 / 是否支持 `tool_choice:"required"` / 是否 reasoning 模型 / 是否支持流式。pydantic-ai 1.107.0 无内置数值（§2）。
- **per-model 默认 max_tokens**：reasoning 模型要给大预算 + 低 reasoning effort（§3.3、§5）。
- **modelscope Qwen3.5 的 tool_choice 兼容修复**：当前 `agent_factory` 走 `OpenAIChatModel` 默认 profile，对 Qwen3.5 仍发 `required` → 空壳。修复选项：
  - 传 `OpenAIModelProfile(openai_supports_tool_choice_required=False)` 让 pydantic-ai 自动降级 `auto`；或
  - 换支持 `required` 的端点（真 OpenAI / DeepSeek / stepfun）；或
  - 改 `output_type` 走 `response_format` json_schema 而非 tool（pydantic-ai 的 `NativeOutput`/`PromptedOutput`，需查 1.107.0 是否对 OpenAIChatModel 暴露）。
  - **注意**：PRD `06-23-web-4` 明确“LLM 兼容性不在本任务范围”，此条仅供后续 implement 任务参考，本任务不实施。
- **DeepSeek V4 thinking 的 `extra_body={"thinking":{"type":"enabled"}}`**：pydantic-ai `thinking` 字段不会生成这个 DeepSeek 私有 body，要我们自己塞 `extra_body`。

### 6.3 设置页字段映射建议（供 implement）
- `llm.max_tokens.classifier` / `llm.max_tokens.portrait` / `llm.max_tokens.normalizer`：number，按模型卡片默认值给（reasoning 模型 ≥4096）。
- `llm.thinking_effort`：枚举 `auto/low/medium/high`（映射 `thinking` 字段；`auto`=不传，用模型默认）。
- `llm.model_card`：静态表（前端展示用），字段 = 上下文 / 最大输出 / tool_choice_required 支持 / reasoning / 流式。可只读展示，选中模型时自动填默认 max_tokens。
- `llm.extra_body`：可选 JSON（高级用户透传端点私有参数）。

## Caveats / Not Found

- **kimi-2.7 256K/32K**：用户提供的数值，**未能从官方文档独立核实**。官方 K2.6 快速开始只写 256K 上下文，未单列“最大输出 32K”；Cloudflare 模型卡也未列 max output。32K 可能是 Moonshot 平台对 API 输出的默认上限，需上 Moonshot 控制台/文档二次确认。
- **step-3.7-flash 最大输出 token 单值**：官方模型页/Quickstart 只写 256K 上下文 + 三档 reasoning，**未公布**“最大输出”硬上限，也未明说 reasoning 是否计入 max_completion_tokens（按 OpenAI 兼容语义 + 我们实测推断计入）。Quickstart 页 fetch 返回空（JS 渲染/反爬），未拿到请求体示例。
- **DashScope deep thinking `extra_body` 字段名**：fetch 被 aliyun 反爬挡回空，从搜索片段看到 `extra_body={"enable_thinking": True}` 字样但未在官方页核实确切字段名/取值，implement 前需以 DashScope 官方文档为准。
- **pydantic-ai 1.107.0 是否支持 `NativeOutput`/`PromptedOutput` 走 `response_format` json_schema 而非 tool**：本次未深入查（PRD 已声明 LLM 兼容性不在本任务范围）。后续若要绕开 `tool_choice:"required"`，需另查 `pydantic_ai.output` 模块。
- **pydantic-ai issue #1559**：fetch 只拿到 issue 首楼，未拿到 maintainers 回复/是否 resolved。从 1.107.0 源码看仍发 `max_completion_tokens`，结论“未加回旧 max_tokens 选项”成立。
- 全局 python 装的是 1.93.0、backend venv 是 1.107.0；本调研**以 venv 1.107.0 为准**（与 PRD/既有 research 一致）。
