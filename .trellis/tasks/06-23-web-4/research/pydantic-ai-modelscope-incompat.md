# pydantic-ai 与 modelscope Qwen 结构化输出不兼容（tool_choice:"required" + max_completion_tokens）

## 一句话

pydantic-ai 1.107.0 对所有 `output_type=<PydanticModel>` 的 agent 用 OpenAI Chat Completions 的新式参数发请求——`tool_choice: "required"` 强制工具调用 + `max_completion_tokens` 限制输出——modelscope 的 `Qwen/Qwen3.5-35B-A3B`（OpenAI 兼容端点）对这两个参数返回**空响应壳**（HTTP 200 但 `choices: null`、`object: ""`），openai SDK 校验失败抛异常，导致所有结构化输出（分类 / 画像 / 标准化）全部失败。

## 环境

- pydantic-ai: `1.107.0`
- openai sdk: `2.43.0`
- 模型端点: modelscope OpenAI 兼容接口
  - base_url: `https://api-inference.modelscope.cn/v1/`（实际经 `_normalize_base_url` 补 `/v1`）
  - 模型: `Qwen/Qwen3.5-35B-A3B`（MoE，35B 总参 / 3B 激活）
- 传输: `OpenAIChatModel` + `OpenAIProvider`，底层 `AsyncOpenAI(httpx.AsyncClient(trust_env=False))`
- 结构化输出方式: pydantic-ai 的 **tool-based structured output**（output_type 是 pydantic 模型 → 注册成单个 function tool → `tool_choice: "required"` 强制模型必须调该 tool → 从 tool 参数里取结构化结果）。**不是** response_format json_schema。

## 现象

跑提取流水线（classifier.classify / portrait.extract / normalizer.normalize）时：

1. 控制台只看到 `Portrait agent.run 失败: ...` / `Classification failed: ...` 这类 warning，LLM 阶段全军覆没。
2. 业务后果链：
   - 分类全失败 → classifier fallback `is_flow_table=False` → **所有表被判「not flow table」→ 全部行落为 `excluded`**（清洗标准化页全显示「排除项」，理由 `classifier: not flow table`）。
   - 画像全失败 → `portrait.extract()` 返回 `None` → Document 表 `portrait` 列为 `null` → 前端 hover 永远显示「画像待生成」。
   - 标准化（stage2）因没有 flow table 永远不进入。

## 根因（已定位到 pydantic-ai 源码行号）

pydantic-ai 在 `output_type` 为 pydantic 模型时，走 tool-calling 路径。`pydantic_ai/models/openai.py` 里构造 Chat Completions 请求体：

```python
# pydantic_ai/models/openai.py（1.107.0）
# 第 1009-1015 行附近
parallel_tool_calls = model_settings.get('parallel_tool_calls', OMIT) if tools else OMIT,
...
tool_choice = tool_choice or OMIT,                 # <- structured output 时 tool_choice = "required"
...
max_completion_tokens = model_settings.get('max_tokens', OMIT),  # <- 把我们的 max_tokens 映射成 max_completion_tokens
```

关键两点：

1. **`tool_choice: "required"`**（第 1233-1241 行 `_get_tool_choice`：`resolved_tool_choice == 'required'` 且 provider supports → 发字符串 `"required"`）。pydantic-ai 对所有有 output schema 的 agent 默认 `tool_choice='required'`，强制模型必须调用那个唯一的结构化输出 tool。
2. **`max_completion_tokens`**（第 1015 行）：pydantic-ai 把我们 `ModelSettings(max_tokens=1500)` 里的 `max_tokens` **直接映射成 OpenAI 的新参数名 `max_completion_tokens`**，而不是旧的 `max_tokens`。

### modelscope 端返回的坏响应

modelscope 的 `Qwen3.5-35B-A3B` 对上述请求返回的 body 形如（HTTP 200）：

```json
{
  "object": "",
  "choices": null,
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

注意三个异常字段：
- `object` 是空串 `""`（正常应是 `"chat.completion"`）
- `choices` 是 `null`（正常应是数组，含 `message.tool_calls`）
- `usage` 全 0

openai sdk 2.43.0 拿到这个响应后在 `ChatCompletion` 模型校验阶段失败（`choices=None` 不满足 `list[ChatCompletionChoice]`，`object=""` 不满足 Literal），抛类似：

```
pydantic.ValidationError ... choices -> input should be a valid list ...
```

被我们业务层的 `except Exception` 捕获 → 当作「LLM 失败」走 fallback。**这是 modelscope 端的行为，不是 pydantic-ai 的 bug**——pydantic-ai 发的是合法的 OpenAI Chat Completions 请求，真正的 OpenAI / DeepSeek / DashScope 都能正常返回带 `tool_calls` 的 choices。问题在于 modelscope 对 `tool_choice:"required"` + `max_completion_tokens` 这两个较新参数的组合处理有问题（疑似它收到后没走 function-calling 分支，返回了空壳）。

## 已做的验证

- 用 `httpx` 直接打 modelscope 同端点，**不带** `tool_choice` / `max_completion_tokens`，普通 chat 请求 → 正常返回完整 choices。证明端点本身可用。
- 用同端点，**带** `tool_choice:"required"` + 一个 function tool 定义 → 返回上述空壳 `choices:null`。
- 后端实测：跑一个任务，DB 里该任务 230 条记录全部 `excluded`、`exclude_reason='classifier: not flow table'`；`documents.portrait` 列全 `null`。与「LLM 全失败 → 全部 fallback」完全吻合。
- public mineru 解析本身端到端正常（17s / 47KB markdown），与 LLM 无关——所以「mineru 解析完成、画像生成失败」这个链路里，mineru 那步是好的，画像失败纯粹是上面这个 LLM 兼容问题。

## 可能的修复方向（供查询/决策，未实施）

### 方向 A：换兼容 `tool_choice:"required"` 的模型端点
- 真 OpenAI、DeepSeek、DashScope（`qwen` 系官方）都支持。换 endpoint + 模型名即可，pydantic-ai 代码不动。**最省事**。
- modelscope 是否有支持 tool_choice:required 的 Qwen 变体，需查 modelscope 文档/issue。

### 方向 B：让 pydantic-ai 不发 `tool_choice:"required"`
- pydantic-ai 对 output_type=pydantic 模型的 tool_choice 是内部硬走的，没有直接开关关掉。可能需要：
  - 改成 `output_type=str`/`bytes` + 自己 parse JSON（放弃 pydantic-ai 的结构化输出保障），或
  - 用 `output_type` 但配合 `ModelSettings` 里某种宽松选项（待查 1.107.0 是否暴露 `tool_choice` 覆盖）。
- 代价：丢掉 pydantic-ai 的 schema 校验 + 自动重试。

### 方向 C：改用 `response_format` json_schema 而非 tool-calling
- pydantic-ai 的 OpenAIChatModel 是否支持「用 json_schema 而非 tool」做结构化输出，需查其 API（`OpenAIChatModelSettings` 里似有 `response_format` 相关，待确认）。modelscope 对 `response_format={"type":"json_object"}` 的支持也需验证。

### 方向 D：降级 openai sdk 参数名
- pydantic-ai 把 `max_tokens`→`max_completion_tokens` 是硬编码映射，无法直接换成旧 `max_tokens`。即便换了，`tool_choice:"required"` 仍是主因，单独换 `max_completion_tokens` 大概率不够。

## 复现脚本（最小）

```python
import asyncio, httpx, json
from pydantic import BaseModel
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI

class Out(BaseModel):
    is_flow: bool

async def main():
    provider = OpenAIProvider(openai_client=AsyncOpenAI(
        base_url="https://api-inference.modelscope.cn/v1/",
        api_key="<KEY>",
        http_client=httpx.AsyncClient(trust_env=False),
    ))
    model = OpenAIChatModel("Qwen/Qwen3.5-35B-A3B", provider=provider,
                            settings=ModelSettings(timeout=60, max_tokens=1500))
    agent = Agent(model, output_type=Out, instructions="...",
                  model_settings=ModelSettings(temperature=0.1, max_tokens=1500, timeout=60))
    try:
        r = await agent.run("判断这是不是流水表：交易日期 金额")
        print("OK", r.output)
    except Exception as e:
        print("FAIL", type(e).__name__, e)

asyncio.run(main())
```

预期：抛 openai/pydantic 校验异常；抓包可见请求体含 `tool_choice:"required"` + `max_completion_tokens:1500`，响应体为空壳 `choices:null`。

## 影响范围（本仓库）

- `backend/app/llm/classifier.py`、`backend/app/llm/portrait.py`、`backend/app/llm/normalizer.py` 三个 agent 全部经 `agent_factory.get_agent()` 构造，全用 output_type=pydantic 模型 → 全部受影响。
- 业务后果：清洗标准化页全排除项 + 画像 hover 全「画像待生成」 + stage2 永不执行。
- 现状：本任务（`06-23-web-4`）的机制都对了（portrait 列、持久化、API、hover 弹窗、批循环、并发限流），卡在这一个 LLM 兼容问题上，导致 ③④ 看不到真实效果。

## 待查问题（拿去搜）

1. modelscope inference：`Qwen3.5-35B-A3B` 是否支持 OpenAI `tool_choice:"required"`（function calling forced）？是否有不返回空壳的变体/参数？
2. modelscope：`max_completion_tokens` vs `max_tokens` 是否被正确接受？空壳 `choices:null` 是否已知 issue？
3. pydantic-ai 1.107.0：能否对 output_type=pydantic 模型禁用 `tool_choice:"required"`、改走 `response_format` json_schema？有无 `OpenAIChatModelSettings` 字段可覆盖？
4. 社区是否有人遇到「modelscope + pydantic-ai 返回 choices:null / object:""」。
