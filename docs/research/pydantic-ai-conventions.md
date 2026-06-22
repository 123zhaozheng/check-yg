# pydantic-ai 官方规范落地参考（v1.107.0 stable, 2026-06-10）

> 本文件是落地 pydantic-ai 的权威依据。所有后端 LLM 改造（classifier/normalizer/portrait + 新增 AI 分析 agent）必须严格按此规范实现。
> 研究来源：pydantic.dev/docs/ai/ 官方文档 + GitHub v1.107.0 源码验证。

## 版本与安装

- **最新稳定版**：v1.107.0（2026-06-10）。**不要用 v2.0.0b7（beta，有 breaking change 风险）**。
- Python 3.10+。
- 安装（只要 OpenAI 兼容端点，slim 版最干净）：
  ```bash
  pip install "pydantic-ai-slim[openai]"
  ```

## 关键 API 改名（v0.6.0 起变更，旧名已删除）

| 旧名（已删除） | v1.107 正确名 |
|---|---|
| `result_type` | **`output_type`** |
| `result.data` | **`result.output`** |
| `result_retries` | `retries={'output': N}` |
| `@agent.result_validator` | **`@agent.output_validator`** |
| `OpenAIModel` | **`OpenAIChatModel`**（Chat Completions）|
| `OpenAIModelSettings` | **`OpenAIChatModelSettings`** |
| `result.usage()` 方法 | **`result.usage` 属性**（不是方法，加括号会报错）|

## OpenAI 兼容 Provider 配置（我们的场景）

```python
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

model = OpenAIChatModel(
    'model-name',                              # 来自 settings.llm.model_name
    provider=OpenAIProvider(
        base_url='https://host/v1',            # 来自 settings.llm.base_url，必须以 /v1 结尾
        api_key='xxx',                         # 来自 settings.llm.api_key
    ),
    settings=ModelSettings(timeout=60, max_tokens=2000),  # timeout 来自 settings.llm.timeout
)
agent = Agent(model, ...)
```

- `base_url` **必须以 `/v1` 结尾**（Chat Completions 走 `/v1/chat/completions`），裸 host 会 404。
- 复用现有 settings：`llm.base_url` / `llm.model_name` / `llm.api_key` / `llm.timeout` 四项，配置层不动，只换调用层。
- ModelSettings 三层覆盖：model 级 `settings=` → agent 级 `model_settings=` → run 级 `model_settings=`（后者赢）。

## Agent 定义与运行

```python
from pydantic_ai import Agent, RunContext

agent = Agent(
    model,
    deps_type=AuditDeps,          # 类型（不是实例）
    output_type=FlowRecord,       # 结构化输出（Pydantic 模型）
    instructions='...',           # 推荐用 instructions 而非 system_prompt（见下）
    retries={'tools': 2, 'output': 2},
    model_settings=ModelSettings(temperature=0.0),
)
result = await agent.run(user_prompt, deps=AuditDeps(...), message_history=history)
print(result.output)              # 验证后的结构化输出
print(result.usage)               # 属性，不是方法
```

- **FastAPI 里必须用 `await agent.run(...)`，禁止 `run_sync()`**（它内部 `loop.run_until_complete`，在运行中的事件循环里会崩）。
- **Agent 在模块级创建一次，跨请求复用**（agent 是无状态配置容器，线程安全）。per-request 数据走 `deps=`。

## 结构化输出 output_type

- 接受 Pydantic `BaseModel` / dataclass / `TypedDict` / `list[X]` / `Literal` / union。
- 默认用 **Tool Output 模式**（每个输出类型注册成输出工具，最可靠）。
- 验证失败自动反馈给模型重试，直到 `output` 重试预算耗尽（默认 1）。
- 落地映射：
  - `classifier` → `output_type=Literal["flow","non_flow"]`（或 bool）
  - `normalizer` → `output_type=list[FlowRecord]`
  - `portrait` → `output_type=DocumentPortrait`
  - AI 分析 → `output_type=AnalysisResult`（你后续定）

## 输出校验器 output_validator

```python
from pydantic_ai import ModelRetry

@agent.output_validator
async def validate(ctx, output: Output) -> Output:
    if not valid(output):
        raise ModelRetry(f'问题: {e}')   # 反馈给模型，消耗 1 次 output 重试
    return output
```

## 工具（tools）—— AI 分析 agent 查标准化流水的落点

```python
@analysis_agent.tool
async def query_transactions(
    ctx: RunContext[AuditDeps],
    start_date: str,
    end_date: str,
    min_amount: float | None = None,
) -> list[dict]:
    """查询日期范围内的标准化流水记录。

    Args:
        start_date: ISO YYYY-MM-DD，含。
        end_date: ISO YYYY-MM-DD，含。
        min_amount: 可选，只返回金额 ≥ 此值的记录。
    """
    rows = await ctx.deps.db.execute(...)
    return [dict(r) for r in rows]
```

- **docstring 自动成为工具描述**，参数描述从 docstring 提取（google/numpy/sphinx 自动识别）。
- 除 `RunContext` 外的参数都成为工具的 JSON schema 参数，Pydantic 校验。
- `ctx.deps` 拿到 per-request 的 DB session / tenant。
- 每工具可单独 `@agent.tool(retries=N)`，`ModelRetry` 触发重试。

## 多轮对话（AI 分析的核心）

```python
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_core import to_json

# 第一轮
result1 = await agent.run('问题1', deps=deps)
history_json = to_json(result1.all_messages())      # 存 DB

# 后续轮：从 DB 读回历史
history = ModelMessagesTypeAdapter.validate_json(history_json)
result2 = await agent.run('追问', deps=deps, message_history=history)
```

- **`message_history` 非空时不再生成新 system prompt**（假设历史里已有）。若持久化时丢了 system prompt，加 `ReinjectSystemPrompt` capability。
- `instructions` vs `system_prompt`：
  - `instructions`（推荐）—— 带 history 时只发当前 agent 的指令，历史的指令被丢弃。
  - `system_prompt` —— 带 history 时保留历史里的 system prompt。
- `conversation_id` 跨轮继承；可用 `agent.run(..., conversation_id='our-thread-id')` 绑定我们的对话线程 ID。
- **消息格式 model-independent**，历史可跨 provider 复用。

## 依赖注入

```python
from dataclasses import dataclass

@dataclass
class AuditDeps:
    db: AsyncSession
    task_id: str

agent = Agent(model, deps_type=AuditDeps)
# 运行时传实例
result = await agent.run(prompt, deps=AuditDeps(db=session, task_id=tid))
```

- `deps_type` 传**类型**，`deps=` 传**实例**——别混。
- `RunContext` 还暴露 `.agent` `.usage` `.messages` `.retry` `.max_retries` `.conversation_id`。

## 错误处理与重试

- 三层重试：agent 级 `retries`（int 同时设 tools+output，或 `{'tools':N,'output':N}`）、每工具 `retries`、run 级 `retries`（只覆盖 output）。
- 瞬时 HTTP 失败（429/5xx）：传 `OpenAIProvider(openai_client=AsyncOpenAI(max_retries=3))` 让 OpenAI SDK 自带重试。
- 防失控：`UsageLimits(request_limit=N, tool_calls_limit=N)`。

## FastAPI 集成官方模式

```python
agent = Agent(model, instructions='...')   # 模块级单例

@app.post('/chat/{thread_id}')
async def chat(thread_id: str, prompt: str, db=Depends(get_db)):
    messages = ModelMessagesTypeAdapter.validate_json(await db.load(thread_id))
    async def stream():
        async with agent.run_stream(prompt, message_history=messages, deps=AuditDeps(db, ...)) as result:
            async for text in result.stream_output(debounce_by=0.01):
                yield text
        await db.save(thread_id, result.new_messages_json())
    return StreamingResponse(stream(), media_type='text/plain')
```

- agent 单例 + per-request deps + `message_history` 持久化 + `run_stream` 流式。
- 这正是我们 AI 分析对话端点的骨架。

## 落地清单（对应后端改造）

1. **装依赖**：`pydantic-ai-slim[openai]` 加入 backend 依赖。
2. **建 agent 工厂**：模块级按 settings 构造 `OpenAIChatModel` + `OpenAIProvider`，复用 `llm.*` settings。
3. **替换 classifier**：`output_type=Literal["flow","non_flow"]`，提示词逐字搬进 `instructions`。
4. **替换 normalizer**：`output_type=list[FlowRecord]`，提示词逐字搬，加 `output_validator` 兜底字段完整性（呼应"不删减"底线）。
5. **替换 portrait**：`output_type=DocumentPortrait`，提示词逐字搬。
6. **新增 AI 分析 agent**：`deps_type=AuditDeps(db, task_id)`，`@agent.tool` 查询标准化流水，`message_history` + `ModelMessagesTypeAdapter` 存对话。tools/prompt 由用户后续完善，本次先给骨架 + 占位。
7. **回归验证**：换框架后，固定输入跑 normalizer，diff 换前换后的标准化输出，验记录 1:1 + 字段无丢（呼应 Q6/Q9 底线）。

## 易错点速查

- `result.usage` 是属性，`result.usage()` 会抛 TypeError。
- `run_sync` 不能在 async 事件循环里用。
- `deps_type` 传类型，`deps=` 传实例。
- `base_url` 要以 `/v1` 结尾。
- union `output_type` 要 `Agent[None, X|Y](...) # type: ignore`，或用 list 形式 `[X, Y]`。
- `Agent('gpt-5')` 裸名非法，要 `Agent('openai:gpt-5')` 或传 Model 实例。
- 多轮 history 非空时不生成新 system prompt；丢了就用 `ReinjectSystemPrompt`。

## 主要文档来源

- 概览/安装：https://pydantic.dev/docs/ai/overview/ , /overview/install/
- Agent：https://pydantic.dev/docs/ai/core-concepts/agent/
- Output：https://pydantic.dev/docs/ai/core-concepts/output/
- 消息历史：https://pydantic.dev/docs/ai/core-concepts/message-history/
- 工具：https://pydantic.dev/docs/ai/tools-toolsets/tools/
- OpenAI 模型：https://pydantic.dev/docs/ai/models/openai/
- 依赖：https://pydantic.dev/docs/ai/core-concepts/dependencies/
- FastAPI chat 示例：https://pydantic.dev/docs/ai/examples/conversational-agents/chat-app/
- 升级指南：https://pydantic.dev/docs/ai/project/changelog/
