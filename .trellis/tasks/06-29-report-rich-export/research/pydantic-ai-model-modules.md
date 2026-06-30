# pydantic-ai model 模块 / 能力协商 / 网关方案调研

- **Query**: pydantic-ai 1.107 是否有内置"模型注册表 / 专用 model 类 / 能力自动协商 / AI 网关"机制，能否取代项目现状（手动 `OpenAIChatModel` + DB 卡片 + 手动 profile 透传能力标志）
- **Scope**: 内部源码（`backend/.venv/Lib/site-packages/pydantic_ai/` + `backend/app/llm/`）
- **Date**: 2026-06-30
- **版本**: `pydantic-ai-slim[openai]==1.107.0`（已确认 `pydantic_ai.__version__ == '1.107.0'`）

---

## TL;DR

1. **pydantic-ai 1.107 确实有内置的"能力协商"机制**，但不是用户想象的"一个 `DeepSeekModel` 类把所有能力写死"，而是 **三层解耦**：`Model`（协议适配，如 `OpenAIChatModel`）+ `Provider`（认证 + `base_url` + 按 `model_name` 选 profile）+ `ModelProfile`（能力标志）。能力知识不在 model 类里，而在 `profiles/<vendor>.py` 的 `xxx_model_profile(model_name)` 函数里（`deepseek_model_profile` 已内置"v4-* 不支持 tool_choice=required"的知识 —— 这正是本项目踩坑的那条）。

2. **但本项目走第三方代理 `http://178.128.209.249:8317/v1`，不是 deepseek 官方端点**，而 `DeepSeekProvider.base_url` 是**硬编码 `https://api.deepseek.com` 的只读 property，无法通过参数覆盖**。所以 `DeepSeekProvider` 内置的 tool_choice 知识在本项目**用不上**。能接任意代理端点的只有 `OpenAIProvider(base_url=...)`（但它不认识 deepseek，profile 走 `openai_model_profile`）或 `LiteLLMProvider(api_base=..., "deepseek/xxx")`（按前缀路由 profile，但需多装 litellm）。

3. **结论：保持现状（`OpenAIProvider(base_url)` + DB 卡片 + 手动 `OpenAIModelProfile` 透传）是本项目当前最合理的选择**，但可以做两个**增量优化**消除"漏传能力标志"的根因（见 §6）。**不要**切 `DeepSeekProvider`（base_url 写死，走不了代理），**暂时不要**引 LiteLLM 网关（多一层依赖，收益不足以抵消复杂度，本项目代理后端单一）。

4. **项目代码注释里"pydantic-ai 1.107.0 无内置模型库，需自维护"（`llm_model.py:46`）这个论断不准确** —— 它有内置 profile 库（`profiles/deepseek.py` 等已有 v4 tool_choice 知识），只是本项目走代理 + 自定义 model_name（`deepseek-v4-flash` 不是 `deepseek:deepseek-v4-flash` 格式）让它自动协商不上。这个认知偏差建议纠正。

---

## 1. 内置 model 类清单

`models/` 目录是**协议适配层**（怎么发 HTTP / 怎么解析响应），与厂商一一对应或共享 OpenAI 协议：

| Model 类 | 文件 | 自带能力 profile？ | 支持自定义 base_url？ |
|---|---|---|---|
| `OpenAIChatModel` | `models/openai.py:758` | 否（profile 来自传入的 provider / 用户构造的 profile） | 是（经 `OpenAIProvider(base_url=...)`） |
| `OpenAIResponsesModel` | `models/openai.py:1758` | 否 | 是 |
| `AnthropicModel` | `models/anthropic.py:450` | 否（profile 来自 `AnthropicProvider`） | 否（端点固定，除非传 `anthropic_client`） |
| `GoogleModel` / `GeminiModel` | `models/google.py:459` / `gemini.py:106` | 否 | 否 |
| `BedrockConverseModel` | `models/bedrock.py:398` | 否 | — |
| `GroqModel` | `models/groq.py:145` | 否 | 否（固定 `groq.com`） |
| `MistralModel` | `models/mistral.py:144` | 否 | 否 |
| `XaiModel` | `models/xai.py:269` | 否 | 否 |
| `CohereModel` | `models/cohere.py:102` | 否 | 否 |
| `HuggingFaceModel` | `models/huggingface.py:136` | 否 | 是（HF endpoint） |
| `OpenRouterModel(OpenAIChatModel)` | `models/openrouter.py:684` | 否（继承自 OpenAIChatModel，profile 由 `OpenRouterProvider` 给） | 是（OpenRouter 自身就是网关） |
| `CerebrasModel(OpenAIChatModel)` | `models/cerebras.py:62` | 否 | 是 |
| `OllamaModel(OpenAIChatModel)` | `models/ollama.py:47` | 否 | 是（本地） |

**重点回答调研问题 1**：

- **没有 `DeepSeekModel` / `MoonshotModel` / `QwenModel` 专用 model 类**。DeepSeek / MoonshotAI / Qwen / ZAI / Harmony 等国内厂商**没有独立的 `Model` 子类**，它们走 `OpenAIChatModel`（OpenAI 兼容协议），能力声明放在 **`profiles/<vendor>.py`**（见下节），并通过 **`providers/<vendor>.py`** 把 profile 函数挂到 `OpenAIChatModel` 上。
- grep `class.*Model` in `models/`（见调研记录）只有上面表里的类，国内厂商一个都没有。
- `models/cerebras.py:62`、`models/ollama.py:47`、`models/openrouter.py:684` 这类"小厂/自部署"做法是**直接继承 `OpenAIChatModel`**，本身不加 profile，profile 全靠传入的 provider。所以**专用 model 类 ≠ 自带 profile**，profile 永远来自 provider。

---

## 2. 专用类 vs 通用 OpenAIChatModel 的能力声明

### 2.1 能力知识真正住在哪里：`profiles/<vendor>.py` 的 profile 函数

证据 —— `profiles/deepseek.py:6-16`：

```python
def deepseek_model_profile(model_name: str) -> ModelProfile | None:
    """Get the model profile for a DeepSeek model."""
    is_r1 = model_name.startswith('deepseek-r1') or model_name == 'deepseek-reasoner'
    is_v4 = model_name.startswith('deepseek-v4-')   # ← 项目踩坑的 deepseek-v4-flash 命中这条
    return ModelProfile(
        ignore_streamed_leading_whitespace=is_r1,
        supports_thinking=is_r1 or is_v4,
        thinking_always_enabled=is_r1,
    )
```

**这就是用户问的"模型参数信手捏来"的内置知识库** —— pydantic-ai 已经知道 deepseek-v4-* 支持 thinking。同类还有 `profiles/qwen.py`、`profiles/moonshotai.py`、`profiles/zai.py`、`profiles/harmony.py`、`profiles/meta.py` 等。

### 2.2 provider 把 profile + base_url + 认证打包，挂到 OpenAIChatModel 上

`providers/deepseek.py:28-62`（关键，**含本项目踩坑那条**）：

```python
class DeepSeekProvider(Provider[AsyncOpenAI]):
    @property
    def base_url(self) -> str:
        return 'https://api.deepseek.com'   # ← 硬编码，无参数覆盖

    @staticmethod
    def model_profile(model_name: str) -> ModelProfile | None:
        profile = deepseek_model_profile(model_name)
        return OpenAIModelProfile(
            json_schema_transformer=OpenAIJsonSchemaTransformer,
            supports_json_object_output=True,
            openai_chat_thinking_field='reasoning_content',
            openai_chat_send_back_thinking_parts='field',
            # ↓↓↓ 本项目踩坑的根因知识，pydantic-ai 已内置 ↓↓↓
            openai_supports_tool_choice_required=(
                model_name != 'deepseek-reasoner' and not model_name.startswith('deepseek-v4-')
            ),
        ).update(profile)
```

`OpenAIChatModel` 怎么吃掉这个 profile —— `models/openai.py:836`：

```python
super().__init__(settings=settings, profile=profile or provider.model_profile)
```

即：**调用方不传 profile 时，自动用 `provider.model_profile(model_name)`**。这就是"专用类自动协商能力"的真相 —— 不是类内置常量，是 provider 的 `model_profile` 静态方法 + 一个按 model_name 判断的 profile 函数。

### 2.3 tool_choice 降级逻辑（确认 pydantic-ai 真的会用这个标志）

`models/openai.py:4194-4210` `_support_tool_forcing`：当 `openai_supports_tool_choice_required=False` 时，`tool_choice='required'` 会被**自动降级为 `'auto'`**（除非用户显式强制 `tool_choice=required`，那会抛 `UserError`）。所以只要 profile 标了 `openai_supports_tool_choice_required=False`，结构化输出（默认走 `tool` 模式 + `required`）就会自动避坑 —— 这正是项目临时解法依赖的机制，证据见 `app/llm/analysis.py:191-194` 注释。

### 2.4 对比现状

| | 专用 provider 路线 | 项目现状 |
|---|---|---|
| 构造 | `OpenAIChatModel('deepseek-v4-flash', provider=DeepSeekProvider())` | `OpenAIChatModel(model, provider=OpenAIProvider(openai_client=...), profile=OpenAIModelProfile(...))` |
| `tool_choice` 知识 | provider 内置（`deepseek-v4-* → False`）| DB 卡片 `supports_tool_choice_required` 列 → `_resolve_agent_params` → `get_agent(supports_tool_choice_required=...)` → `OpenAIModelProfile(openai_supports_tool_choice_required=False)` |
| `thinking` 知识 | provider 内置（`supports_thinking` 自动设）| DB 卡片 `is_reasoning` + `default_thinking` → 手动 `OpenAIModelProfile(supports_thinking=True)` |
| base_url | **写死 `api.deepseek.com`**（见 §3） | DB 卡片 `provider_base_url`（任意端点） |

**核心结论**：专用 provider 的优势是"能力知识免配置"，但它的 base_url 写死，本项目走代理用不上；通用 `OpenAIProvider(base_url)` 优势是"任意端点通吃"，但 profile 走 `openai_model_profile`，不认识 deepseek，所以能力必须手动补。**这是项目当前架构取舍的直接来源，不是"没找到好方案"。**

---

## 3. 第三方代理场景适用性（本项目核心约束）

**项目用 `http://178.128.209.249:8317/v1`，背后可能是 deepseek/其他，但不是 deepseek 官方 `api.deepseek.com`。**

### 3.1 `DeepSeekProvider` base_url 硬编码，无法覆盖

`providers/deepseek.py:35-37`：

```python
@property
def base_url(self) -> str:
    return 'https://api.deepseek.com'   # 只读 property，没有 setter
```

`__init__`（`providers/deepseek.py:76-98`）只接受三种入参，**全部绕不开 base_url**：
- `api_key=`（走默认 `api.deepseek.com`）
- `openai_client=AsyncOpenAI(...)`（可以塞自定义 base_url，但这就**退化成了"自己构造 client"**，profile 仍是 `DeepSeekProvider.model_profile` —— 见下）
- `http_client=httpx.AsyncClient(...)`（只换底层 transport，base_url 还是 `api.deepseek.com`）

注意：项目现状其实**已经在用 `openai_client=AsyncOpenAI(base_url=..., ...)` 这条路**（`agent_factory.py:82-88`），只是套的是 `OpenAIProvider` 而非 `DeepSeekProvider`。理论上可以改成 `DeepSeekProvider(openai_client=AsyncOpenAI(base_url=normalized_url, ...))` —— 这样**既能自定义 base_url，又能白嫖 `deepseek_model_profile` 的 tool_choice 知识**。**这是一条之前没人想到的中间路线**（见 §6 优化 B）。

### 3.2 能接任意 OpenAI 兼容端点的方式

| 方式 | 自定义 base_url | 自动协商能力 | 适用本项目 |
|---|---|---|---|
| `OpenAIProvider(base_url=...)` 或 `openai_client=AsyncOpenAI(base_url=...)` | ✅ | ❌（只走 `openai_model_profile`） | ✅ 现状 |
| `DeepSeekProvider(openai_client=AsyncOpenAI(base_url=...))` | ✅（经 client 注入） | ✅ deepseek 专用 | ⚠️ 仅当后端确为 deepseek 时（见 §6-B） |
| `LiteLLMProvider(api_base=..., "deepseek/xxx")` | ✅ | ✅（按 `provider/` 前缀路由，见 §5） | ⚠️ 需装 litellm |
| `OpenRouterModel` / `gateway/` 前缀 | ✅ | ✅ | ❌（需走它们自己的网关，不是裸代理） |

**回答调研问题 3**：`DeepSeekProvider` base_url 确实硬编码，但**有 `openai_client` 注入这条缝**（项目现状已经用了 client 注入，只是套错 provider）。通用 `OpenAIChatModel` + 自定义 `base_url` 不是"唯一"方式，但是最通用、对后端模型最不假设的方式。

---

## 4. ModelProfile 协商机制

### 4.1 继承链

`profiles/__init__.py:41-180` 定义基类 `ModelProfile`（dataclass），核心字段：

- `supports_tools` / `supports_json_schema_output` / `supports_json_object_output` / `default_structured_output_mode`（默认 `'tool'`，这就是为什么结构化输出默认走 tool + required）
- `supports_thinking` / `thinking_always_enabled` / `thinking_tags`
- `ignore_streamed_leading_whitespace`
- `supported_native_tools`

provider 专用 profile 继承 `ModelProfile` 并加 `openai_` 前缀字段（设计目的写在 `profiles/openai.py:62`："ALL FIELDS MUST BE `openai_` PREFIXED SO YOU CAN MERGE THEM WITH OTHER MODELS"）—— 例如 `OpenAIModelProfile`（`profiles/openai.py:59`）多出 `openai_supports_tool_choice_required`（默认 `True`，`profiles/openai.py:104`）、`openai_supports_strict_tool_definition`、`openai_chat_thinking_field` 等十几个 OpenAI 协议特有字段。

### 4.2 有没有"model_name → profile 注册表"？

**有，但不是一张静态 dict，而是"provider 名 + provider.model_profile(model_name) 函数"的两级查表**：

1. 第一级：`parse_model_id("deepseek:deepseek-v4-flash")` → `("deepseek", "deepseek-v4-flash")`（`models/__init__.py:983-1015`）
2. 第二级：`infer_provider_class("deepseek")` → `DeepSeekProvider`（`providers/__init__.py:151-154`）→ `DeepSeekProvider.model_profile("deepseek-v4-flash")` → 调 `deepseek_model_profile` + 叠加 OpenAI 特化

顶层入口 `infer_model_profile(model: str)`（`models/__init__.py:1018-1048`）一次性完成上述查表，返回 profile；未知 provider 返回 `DEFAULT_PROFILE`（`profiles/__init__.py:180`，全是默认值）。

### 4.3 有没有内置"已知模型能力表"（类似 litellm model_cost）？

**部分有**：
- **已知 model_name 清单**：`models/_known_model_names.py`（`KnownModelName` Literal，约 400 个，含 `deepseek:deepseek-v4-flash`、`gateway/openai:gpt-5`、`heroku:glm-4-7` 等）—— 但这只是**类型提示 + 文档**，不是能力表，不参与运行时协商。
- **能力知识**：散落在各 `profiles/<vendor>.py` 的 `if model_name.startswith(...)` 分支里（如 `profiles/openai.py:193` `openai_model_profile` 按 `gpt-5.1`/`o` 前缀判 reasoning；`profiles/deepseek.py` 按 `r1`/`v4` 前缀判）。
- **没有** litellm 那种 `model_cost / max_tokens / supports_function_calling` 的统一静态大表。能力是"按 vendor 分文件的函数式判定"，不是中央注册表。

### 4.4 关键：本项目为什么自动协商不上

项目 DB 卡片的 `model_name` 是裸字符串 `deepseek-v4-flash`（`llm_model.py:41`），**不是 `deepseek:deepseek-v4-flash` 格式**，且套的是 `OpenAIProvider`（`agent_factory.py:81`）。所以：
- `parse_model_id("deepseek-v4-flash")` → `(None, "deepseek-v4-flash")`（没有 `:` 前缀，`models/__init__.py:1014-1015` 返回 None provider）
- → `infer_model_profile` 返回 `DEFAULT_PROFILE`
- → `OpenAIProvider.model_profile` 走 `openai_model_profile`（不认识 v4）

**这正是 §6 优化 A 的切入点**：如果 DB 卡片多存一个"provider 标签"（如 `deepseek`），就能让 `infer_model_profile` / 专用 provider 命中，白嫖内置 profile。

---

## 5. 网关层方案

### 5.1 pydantic-ai 内置的"网关"机制

pydantic-ai 1.107 自己有两个网关抽象：

1. **`LiteLLMProvider`**（`providers/litellm.py`）—— 包装 LiteLLM，**按 `model_name` 的 `provider/` 前缀自动路由 profile**（`providers/litellm.py:48-83`）：

   ```python
   provider_to_profile = {
       'anthropic': anthropic_model_profile, 'openai': openai_model_profile,
       'deepseek': deepseek_model_profile, 'moonshotai': moonshotai_model_profile,
       'qwen': qwen_model_profile, ...
   }
   if '/' in model_name:
       provider_prefix, model_suffix = model_name.split('/', 1)
       if provider_prefix in provider_to_profile:
           profile = provider_to_profile[provider_prefix](model_suffix)
   ```
   构造时传 `api_base=...`（`providers/litellm.py:105-137`）可指自定义端点。**这是"网关式能力协商"最完整的内置方案**：一个 provider + `model="deepseek/deepseek-v4-flash"` + `api_base=代理URL`，自动拿到 deepseek profile。代价：多装 `litellm` 包（项目 `pyproject.toml` 目前没装）。

2. **`gateway/` 前缀 + `gateway_provider()`**（`providers/gateway.py`）—— 这是 **Pydantic AI 自家的托管网关**（`https://gateway.pydantic.dev/proxy`，`providers/gateway.py:139`），需要 `PYDANTIC_AI_GATEWAY_API_KEY`，支持 `gateway/openai:...`、`gateway/anthropic:...`、`gateway/bedrock:...` 等（见 `models/_known_model_names.py:109-203`）。**与本项目"裸代理 IP"场景无关** —— 它是 SaaS 网关，不是自部署 OpenAI 兼容代理。

3. **`FallbackModel`**（`models/fallback.py:69`）—— 多模型容灾，不是路由网关，略。

### 5.2 LiteLLM 与 pydantic-ai model 抽象的关系

- LiteLLM 是**独立的 Python 库**，`litellm.completion(model="deepseek/deepseek-chat", ...)` 内部自己做 provider 路由 + 能力适配。
- pydantic-ai 的 `LiteLLMProvider` **不是**在 model 抽象里"内嵌 litellm 能力表"，而是**把 LiteLLM 当 backend transport 用**（`providers/litellm.py:125-137` 注释："The actual API calls will be intercepted and routed through LiteLLM"），profile 仍由 pydantic-ai 自己的 `provider_to_profile` dict 决定。
- 所以"在 pydantic-ai 里用 LiteLLM 做 backend" = `OpenAIChatModel(model, provider=LiteLLMProvider(api_base=...))`，能力协商走 pydantic-ai profile，HTTP 走 litellm。

### 5.3 项目现状的"DB 卡片 + 阶段指派"是不是自研网关？

**是，本质上是一层薄自研网关**，但它网的是**"任务阶段 → 选哪张卡"**（`LLMModelAssignment` 按阶段指派），不是**"model_name → 能力/profile"**。两层职责：
- **pydantic-ai model 抽象**：管"给定一个 (provider, model_name)，怎么发请求 / 解析响应 / 设能力标志"。
- **项目 DB 卡片 + `_resolve_agent_params`**：管"给定一个业务阶段（report_generation），用哪个端点、哪个 model、max_tokens、thinking 档"。
- **LiteLLM/Portkey**：管"多 provider 统一路由 + 计费 + fallback"。

项目当前**不需要**第三层 —— 代理后端单一（一个 IP:port），没有多 provider 路由需求。所以引 LiteLLM 是"为了用一个 profile 自动协商，拖进一个完整网关库"，性价比低（见 §6）。

---

## 6. 项目现状评估 + 建议

### 6.1 三条路对比

| 路径 | 描述 | 优势 | 劣势 | 对本项目（走第三方代理 `178.128.209.249:8317`）适用性 |
|---|---|---|---|---|
| **现状** | 通用 `OpenAIProvider(openai_client=AsyncOpenAI(base_url=...))` + `OpenAIChatModel` + DB 卡片 + 手动 `OpenAIModelProfile(openai_supports_tool_choice_required=..., supports_thinking=...)` 透传 | 任意端点通吃 / 能力完全可控 / 无额外依赖 / 多阶段缓存复用（`agent_factory._agent_cache`） | 每个能力标志要手动 wire（DB 列 → resolve → factory → profile），易漏（本次 tool_choice 就是漏 wire） | ✅ 已落地，坑已填 |
| **专用 provider** | `DeepSeekProvider` / `OpenAIProvider` 等 | profile 内置免配（`deepseek-v4-* → tool_choice=False` 自动） | base_url 多数硬编码；DeepSeek 仅 `openai_client` 注入可绕；后端模型不一定是 deepseek 时 profile 会错配 | ⚠️ 仅当代理后端**确知**是某 vendor 时可用（见 6-B） |
| **网关层** | `LiteLLMProvider(api_base=..., "deepseek/xxx")` 或 Portkey/OpenRouter | 能力按前缀自动协商 / 多 provider 路由 / fallback | 多一层依赖（litellm）/ 与 pydantic-ai model 抽象部分重叠 / 本项目代理单一，路由能力用不上 | ❌ 过度设计 |

### 6.2 明确推荐

**主结论：保持现状架构（`OpenAIProvider(base_url)` + DB 卡片 + 手动 profile 透传）。** 理由：
1. 本项目核心约束是"走任意第三方 OpenAI 兼容代理"，专用 provider 的 base_url 硬编码与该约束冲突（§3）。
2. 本项目代理后端单一，无多 provider 路由需求，引 LiteLLM 网关是过度设计（§5.3）。
3. 现状架构已在生产，且本次 tool_choice 的坑**已通过 `_resolve_agent_params` + `get_agent(supports_tool_choice_required=...)` 填上**（`analysis.py:195`、`agent_factory.py:67,118-119`），没有遗留缺陷。

**但建议做两个增量优化（消除"漏传能力标志"的根因，不需要现在做，供后续 task 评估）：**

> 优化 A（推荐，低成本）：**在 DB 卡片 `LLMModel` 加一列 `provider_tag`（如 `deepseek` / `openai` / `moonshotai`）**，`agent_factory` 构造时用它走 `infer_model_profile(f"{provider_tag}:{model_name}")` 拿到 pydantic-ai 内置 profile 作为**基底**，再用 DB 卡片的显式标志（`supports_tool_choice_required` 等）做 `.update()` 覆盖。这样能力知识"先抄 pydantic-ai 内置库，再按卡片微调"，既保留任意 base_url，又不再每条标志都从零手 wire。证据可行：`OpenAIModelProfile.update()`（`profiles/openai.py` 经 `ModelProfile.update`，`profiles/__init__.py:151-161`）正是为"基底 + 覆盖"设计的。

> 优化 B（可选，仅当代理后端确知是 deepseek）：把 `agent_factory.py:81` 的 `OpenAIProvider(openai_client=AsyncOpenAI(base_url=normalized_url, ...))` 换成 `DeepSeekProvider(openai_client=AsyncOpenAI(base_url=normalized_url, ...))` —— base_url 经 client 注入绕过硬编码（§3.1），同时白嫖 `deepseek_model_profile` 的 v4 tool_choice 知识。**风险**：若代理后端其实不是 deepseek（比如换成了 qwen），profile 会错配。所以前提是卡片能标 provider，又绕回优化 A。

> 优化 C（文档纠正）：`backend/app/models/llm_model.py:46` 注释"pydantic-ai 1.107.0 无内置模型库，需自维护——research §2/§5"不准确。应改为"pydantic-ai 有内置 profile 库（`profiles/<vendor>.py`），但走自定义代理端点 + 非 `provider:model` 格式 model_name 时自动协商不上，故仍需卡片维护能力标志"。这条认知纠正不影响代码，但避免后续误导。

### 6.3 不推荐的做法

- ❌ **切 `DeepSeekProvider` 作为唯一通用方案**：base_url 硬编码，且代理后端未必是 deepseek。
- ❌ **引 LiteLLM/Portkey 网关**：本项目无多 provider 路由需求，多一层依赖收益不足。
- ❌ **删 DB 卡片的 `supports_tool_choice_required` 列、改全靠 pydantic-ai 内置 profile**：本项目 model_name 不是 `provider:model` 格式，内置 profile 协商不上，删了就没法配了。

---

## 附：关键源码引用

### pydantic-ai 1.107（`backend/.venv/Lib/site-packages/pydantic_ai/`）

- `models/_known_model_names.py:107` — `deepseek:deepseek-v4-flash` 在已知清单（含 `gateway/`、`heroku:` 等网关前缀）
- `profiles/__init__.py:41-180` — `ModelProfile` 基类 + 全部能力字段 + `update()` 合并机制
- `profiles/deepseek.py:6-16` — `deepseek_model_profile`：v4-* 支持 thinking
- `profiles/qwen.py:11-30` — `qwen_model_profile`：qwen-3-coder `openai_supports_tool_choice_required=False`
- `profiles/moonshotai.py:6-8` / `profiles/zai.py:6-11` — 国内厂商 profile（zai 返回 None，能力在 provider 层）
- `profiles/openai.py:59-251` — `OpenAIModelProfile`（含 `openai_supports_tool_choice_required`，默认 True）+ `openai_model_profile`
- `providers/__init__.py:114-268` — `infer_provider_class`：provider 名 → Provider 类（含 `deepseek`/`moonshotai`/`alibaba`/`litellm` 等）
- `providers/__init__.py:271-304` — `infer_provider`：`gateway/` 前缀走 `gateway_provider`
- `providers/deepseek.py:35-37` — **`base_url` 硬编码 `https://api.deepseek.com`**（只读 property）
- `providers/deepseek.py:43-62` — `DeepSeekProvider.model_profile`：内置 `deepseek-v4-*` 不支持 `tool_choice=required`
- `providers/deepseek.py:76-98` — `__init__` 只接受 `api_key`/`openai_client`/`http_client`，无 base_url 参数
- `providers/openai.py:37-88` — `OpenAIProvider` 接受 `base_url` 参数（本项目用的）
- `providers/litellm.py:48-83` — `LiteLLMProvider.model_profile` 按 `provider/` 前缀路由 profile
- `providers/litellm.py:105-137` — `LiteLLMProvider(api_base=...)` 接自定义端点
- `providers/gateway.py:119-207` — Pydantic AI 自家托管网关（`gateway.pydantic.dev`，需 API key）
- `models/openai.py:836` — `OpenAIChatModel` 默认 `profile = profile or provider.model_profile`（关键：不传 profile 就走 provider）
- `models/openai.py:1239-1241` — `tool_choice='required'` 经 `_support_tool_forcing` 判定
- `models/openai.py:4194-4210` — `_support_tool_forcing`：`openai_supports_tool_choice_required=False` 时降级为 `'auto'`
- `models/__init__.py:983-1048` — `parse_model_id` + `infer_model_profile`（model_name → profile 查表入口）

### 项目现状（`backend/app/`）

- `app/llm/agent_factory.py:81-89` — 现状：`OpenAIProvider(openai_client=AsyncOpenAI(base_url=normalized_url, ...))`
- `app/llm/agent_factory.py:110-125` — 现状：手动 `OpenAIModelProfile(supports_thinking=..., openai_supports_tool_choice_required=False)` 透传
- `app/llm/agent_factory.py:138-210` — `get_agent`：按参数缓存 agent
- `app/llm/analysis.py:154-196` — `_resolve_agent_params`：DB 卡片字段 → agent 连接参数（含 `supports_tool_choice_required`）
- `app/models/llm_model.py:46` — 注释"pydantic-ai 无内置模型库"（不准确，见 §6.2-优化C）
- `app/models/llm_model.py:50-52` — `LLMModel.supports_tool_choice_required` DB 列

## Caveats / 未查到

- LiteLLM 实际"自动能力协商"的深度（是否像 litellm 那样有 model_cost/max_tokens 大表）未深入查 litellm 库源码（项目未装 litellm，`.venv` 无该包）—— 本次只查了 pydantic-ai 侧的 `LiteLLMProvider` 包装。
- 第三方代理 `178.128.209.249:8317` 后端实际是 deepseek 还是其他厂商，**代码层无法确认**，需运维/抓包确认。若确知是 deepseek，§6.2 优化 B 可行。
- 未查 pydantic-ai GitHub issue/PR 关于"自定义 base_url + 专用 provider"的官方表态（本次纯源码调研，未做 web search）。源码 `DeepSeekProvider(openai_client=...)` 这条 client 注入路径的存在本身已说明官方留了这条缝。
