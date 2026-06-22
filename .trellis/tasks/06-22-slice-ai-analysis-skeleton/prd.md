# S6 AI 分析骨架闭环

## 目标
AI 分析页（Tab4）骨架闭环。**agent tools 留接口、占位实现**——真实 prompt/tools 由用户后续接。前端完整 UI + 后端 Finding 模型 + pydantic-ai analysis_agent 骨架（deps + tool 签名 + output_type + 占位 instructions）+ 4 接口。

## 硬底线（不可违反）
1. **单色原则**：风险等级用**灰阶 + 形状双重编码**，禁红黄绿。高=黑底白字方块 / 中=深灰 / 低=浅灰。对话气泡：AI 浅灰底 / 用户黑底白字。
2. **Chrome 108 渲染**：禁裸写 color-mix/oklch/lab，用 9 级 ink token。
3. **agent 接入点结构正确**：遵循 `docs/research/pydantic-ai-conventions.md` v1.107.0——deps_type 传类型、deps= 传实例、@agent.tool 工具签名、ModelMessagesTypeAdapter 存对话、message_history 多轮。便于用户后续接真实 tools/prompt。
4. **提示词保真**：S6 是**新 agent**（非 legacy 搬运），instructions 占位但结构要对。**禁改** normalizer/classifier/portrait 的 SYSTEM_PROMPT。`test_llm_parity.py` 仍绿。
5. **不删减**：agent tools 查 flow_records **只读不改**，不删任何记录。`test_cleaning_no_drop.py` 仍绿。

## 实施决策（2026-06-22 切片定稿）

### 决策1：Finding 模型
新表 `findings`：id / task_id(FK tasks) / type(String，异常类型如大额/高频/对手异常) / severity(String: high|medium|low) / description(Text) / counterparty(String nullable) / amount(String nullable) / confidence(Float 0-1) / status(String: pending|accepted|ignored, default pending) / comment(Text nullable) / created_at / updated_at。
- Alembic migration（revises S5 head `42add7788eef`）。env.py 登记。
- 无 jsonb 字段（全是标量），简单。

### 决策2：analysis_agent 骨架（pydantic-ai）
- `backend/app/llm/analysis.py`（新）：
  - `AuditDeps` dataclass/pydantic：`db: AsyncSession` + `task_id: int`。
  - `AnalysisResult` output_type（pydantic，types.py 或 analysis.py 内）：findings 列表（每项 type/severity/description/counterparty/amount/confidence）+ summary。
  - `SYSTEM_PROMPT_ANALYSIS` = 占位 instructions（明确标注"占位，用户后续接真实审查逻辑"，结构对齐 conventions.md：任务/工具说明/输出格式）。
  - `get_analysis_agent()`：复用 `agent_factory.get_agent(AnalysisResult, SYSTEM_PROMPT_ANALYSIS, max_tokens=...)`。
  - `@agent.tool` 工具签名（留接口，实现可查 flow_records 返占位/真实数据）：
    - `query_transactions(ctx, *, channel?, limit?)` → 查 standard 记录
    - `query_by_counterparty(ctx, *, counterparty)` → 按对手查
    - `query_by_amount_range(ctx, *, min_amount, max_amount)` → 按金额区间查
    - 每个工具 docstring 成工具描述，参数成 JSON schema。
  - `async def run_analysis(deps) -> AnalysisResult`：调 agent.run，**占位返回**（真实 prompt/tools 用户后续接；本切片 agent.run 可用占位 instructions 跑通结构，或直接返占位 findings 不调 LLM——选**返占位 findings 不调真实 LLM**，避免占位 prompt 产生垃圾输出，结构对了即可）。
- `backend/app/llm/chat.py` 或 analysis.py 内：多轮对话骨架，`ModelMessagesTypeAdapter` 序列化/反序列化 message_history，`async def chat(deps, message_history_json, user_msg) -> (reply, new_history_json)`，**占位回复**（不调真实 LLM 或调了返占位）。

### 决策3：对话历史持久化
- Task.config jsonb 存 `analysis_chat_history`（ModelMessagesTypeAdapter 序列化的 JSON 字符串）。或新表 `analysis_chats`。决策：**存 Task.config.analysis_chat_history**（轻量，单任务单对话线程，不另建表）。

### 决策4：4 接口（tasks.py）
- `POST /api/tasks/{id}/analyze`：触发分析。占位：建若干占位 Finding 行（或调 run_analysis 占位）+ 写 task.config.last_analysis_at 时间戳。返 AnalysisResult 摘要 + findings 列表。
- `GET /api/tasks/{id}/findings?severity=&status=`：返 Finding 列表（按 severity 排序 high>medium>low，同 severity 按 confidence 降序）。
- `PATCH /api/findings/{id}`：body {status?: accepted|ignored, comment?}。更新 Finding。返更新后 Finding。
- `POST /api/tasks/{id}/analyze/chat`：body {message: string}。多轮对话，读 Task.config.analysis_chat_history → chat() → 占位回复 + 存回。返 {reply: string}。
- owner-only 复用 `_load_owned_task`（PATCH /findings/{id} 要校验 finding.task 的 owner）。

## 前端范围（`frontend/src/routes/__authenticated/tasks/$id/analyze.tsx`）
新设计 AI 分析页（无 stitch 源稿，按任务描述 + docs/web-pages-design.md §C4 自创，单色）：
- **顶部分析控制条**：「开始分析」黑底主按钮 + 快速/深度模式描边单选（segmented）+ 上次分析时间（灰文）+ 模型参数（灰文）。
- **分析中**：顶部灰阶进度条 + 阶段文字（"正在分析…"/"完成"）。本切片分析是占位/快速，进度条可简单走一个占位动画或立即完成。
- **左侧异常发现列表**：按风险等级排序。风险等级**灰阶+形状双编码**：高=黑底白字方块（bg-ink-900 text-ink-100）/中=深灰（bg-ink-700 text-ink-100）/低=浅灰（bg-ink-300 text-ink-700）。选中项左侧黑竖条（border-l-2 border-ink-900）。每项显 severity 标 + description 摘要 + confidence。
- **右侧异常详情**：AI 推理摘要 + 关联记录列表（引用 flow_records，本切片可显占位或关联记录 id）+ 时间分布黑白灰小图（简单 bar，灰阶）+ 置信度灰阶水平条（bg-ink-200 底 + bg-ink-900 填充宽度=confidence）+ 三按钮（采纳为告警/忽略/添加备注 → PATCH）。
- **底部多轮对话区**：气泡（AI 浅灰底 bg-ink-200 text-ink-900 / 用户黑底白字 bg-ink-900 text-ink-100）+ 输入框 + 发送按钮。发送 → POST chat → 占位回复追加。agent 可在对话里引用查到的记录（占位回复里带记录引用样式）。
- TanStack Query 拉 findings，mutation 跑 analyze/patch/chat。

## api.ts（只追加）
Finding / AnalysisResult / ChatResponse 类型 + startAnalysis(taskId, mode) / listFindings(taskId, params) / patchFinding(id, body) / chatAnalyze(taskId, message) 函数。apiFetch 主体不动。

## hooks
useFindings / useStartAnalysis / usePatchFinding / useChatAnalyze（后者维护本地消息列表 + 发送 mutation）。

## 验收
- chrome108 渲染正常，风险等级纯灰阶+形状表达（无红黄绿）。
- 对话 UI 闭环（哪怕占位回复）。
- Finding CRUD 通（创建 via analyze、列表、patch status/comment）。
- agent 接入点结构正确（deps_type + @agent.tool 签名 + ModelMessagesTypeAdapter + message_history），便于用户后续接真实 tools/prompt。
- 后端全量测试绿（含 test_llm_parity + test_cleaning_no_drop 回归），前端 build 通过。

## 不做（留给后续切片）
- 真实审查 prompt + tools 实现（本切片骨架 + 占位）。
- 报告（S7）、导出（S8）。
- 真实模型回归（用户推迟）。
