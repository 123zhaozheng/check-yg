# AI 审查维度落地 + 悬浮追问 Agent + 维度沉淀

> 把 `app/llm/analysis.py` 占位骨架接到真实能力。核心范式：
> **维度 = 结构化提示词（不是工具、不是代码规则）**；一套固化的只读表访问工具
> 被所有维度共享；跑分析 = 每个 enabled 维度各跑一次 agentic agent.run；追问 =
> 悬浮框多轮对话；沉淀 = `create_dimension` 工具填字段 → 服务端拼模板 → 落库。
> 因为维度是提示词，沉淀新维度**零代码**，"固化后代码不好固化"难点自解。

## 现状（代码事实）

- `app/llm/analysis.py`：纯占位。`SYSTEM_PROMPT_ANALYSIS` 占位；3 个只读工具
  (`query_transactions`/`query_by_counterparty`/`query_by_amount_range`) 已搭好查
  `flow_records.record_type="standard"`；`run_analysis`/`chat` 不调 LLM 返占位。
- `app/routers/tasks.py`：`POST /tasks/{id}/analyze`（调 `run_analysis` 落 Finding +
  写 `task.config.last_analysis_at`）、`GET /tasks/{id}/findings`、
  `PATCH /findings/{id}`、`POST /tasks/{id}/analyze/chat`（历史存
  `task.config.analysis_chat_history`，单线程）。
- `Finding` 模型：type/severity/description/counterparty/amount/confidence/
  status(pending|accepted|ignored)/comment，全标量。
- `FlowRecordRow`：`record_type` standard|unparsed|excluded；standard 有
  transaction_time(str)/counterparty_name/counterparty_account/amount(str)/
  raw_amount/summary/transaction_type。
- 旧 `src/llm/audit_agent.py`（legacy 未搬）：4 条硬编码规则 + `_parse_amount`/
  `_parse_datetime` 多格式解析——**解析逻辑要复用**，规则逻辑**不搬**（改提示词）。
- 关键词库 `KeywordCard`+`KeywordTerm`+`KeywordHit`：数据驱动 CRUD 范式，维度库复刻。
- 阶段模型卡 `STAGE_AI_ANALYSIS` / `STAGE_AI_QA`：预留映射位，本任务接通生效。
- 前端 `tasks/$id/analyze.tsx`：左 findings 列表 + 右详情（时间分布 seeded 假数据，
  关联记录占位）+ 底部直铺 `<ChatPanel>`。`use-analysis.ts` 已有 hooks。
- WebSocket 基建（`task_progress` 消息）已就绪，跑分析进度走它。

---

## 一、核心架构（范式）

```
┌─ 固化只读工具集（共享，底层访问 flow_records 等表）────────────┐
│ get_task_summary / query_by_time / query_by_amount /          │
│ query_by_counterparty / query_burst                           │
└───────────────────────────────────────────────────────────────┘
          ▲                              ▲
          │挂载                          │挂载 + 多挂 query_findings + create_dimension
┌─────────┴──────────┐         ┌────────┴──────────────┐
│  维度 agent         │         │  追问 agent（悬浮框）  │
│  output=结构化      │         │  output=文本           │
│  instructions=维度  │         │  多轮对话              │
│   提示词（动态）    │         │  create_dimension 沉淀 │
│  agentic 单次 run   │         │                        │
│  内多步工具循环     │         │                        │
│  STAGE_AI_ANALYSIS  │         │  STAGE_AI_QA           │
└────────────────────┘         └────────────────────────┘
```

**跑分析**：`POST /analyze`（异步 background task）→ 对每个 `enabled=true` 维度
**串行**跑维度 agent → 每跑完一个 WebSocket 推进度 + finding 实时增量入左侧列表。

**维度 = 提示词**：每个维度 = `{name, purpose, steps, judgment, severity}`，服务端
用固定模板拼成完整 prompt 存库。跑分析时该 prompt 注入维度 agent 的 instructions。
**新维度沉淀 = 加一行提示词，不改码。**

---

## 二、固化只读工具集（5 个，两 agent 共享）

改造现有 `analysis.py` 的 3 个工具为这套，新增 2 个。用 pydantic-ai `Toolset` 打包。
**所有工具底层查 `flow_records WHERE task_id=? AND record_type='standard'`**，金额/时间
解析复用 legacy `_parse_amount`/`_parse_datetime`。**所有工具带 limit 防爆 context**。

| 工具 | 参数 | 行为 |
|---|---|---|
| `get_task_summary` | — | 任务笔数/standard·unparsed 计数/金额合计/时间跨度。**只返聚合数**，limit 兜底 |
| `query_by_time` | `start,end`(ISO) 或 `hours`(list) | 按交易时间窗口查；**默认剔除时分秒==00:00:00（不可关）**——全0是"只记日期"噪音 |
| `query_by_amount` | `min,max`(float) 或 `mode`(large/round/evasion) | 按金额区间；mode 让 agent 不用算阈值（large=≥min,round=尾随≥4个0,evasion=阈值下浮band内） |
| `query_by_counterparty` | `name`, `min_count?` | 按对手方；带 min_count 一步出"≥N笔的对手方" |
| `query_burst` | `window_minutes`, `min_count` | 短间隔簇/快进快出（时间聚类逻辑封进工具，不让 agent 拼） |

- limit：明细类默认 200，硬上限 1000，agent 可调。
- **不设** 泛查全表工具（防爆 context）；摸底用 summary，下钻用带参数工具。
- `steps.tool`（create_dimension 入参）限这 5 个 + `query_findings` 的白名单，防 agent 编造。

---

## 三、维度提示词固定模板（服务端拼装）

跑分析与追问沉淀出的维度**共用一套模板**。模板固定段 + 维度字段段：

```
## 维度：{name}  （默认severity: {severity}）

## 任务
你是银行/支付流水审计助手，针对本任务 standard 流水检测以下异常。
{purpose}

## 可用工具（只读，已剔除无时分秒记录，均带limit防爆context）
- get_task_summary / query_by_time / query_by_amount /
  query_by_counterparty / query_burst
按需调用，想调几次调几次，查够再下结论。

## 分析步骤
{steps}                      ← 来自维度 steps 字段（list[{tool,params}]）格式化

## 判定标准（决定是否产出finding及severity）
{judgment}                   ← 零命中则不产出，不要编造

## 输出（few-shot 样例）
{样例：一条好 DimensionFinding 的结构 + 一条零命中空输出的结构}
产出 DimensionFinding：type/severity/counterparty(可空)/amount(合计)/
detail_text(自然语言分析，引用真实笔数与样本)/evidence_record_ids/confidence。
零命中 → 空 findings，detail_text="未发现X异常"。
```

`purpose`/`steps`/`judgment` 随维度变；工具说明段 + few-shot 段固定。

---

## 四、预冻 5 个 system 维度（迁移 seed，enabled=true）

| 维度 | purpose | steps 核心 | judgment |
|---|---|---|---|
| 夜间交易 | 非营业时段(22:00–次日06:00)交易 | query_by_time(hours=[22,23,0,1,2,3,4,5]) | 命中 high；占总量>20% 加 severity |
| 大额交易 | 单笔大额（≥5万，现金监管口径） | query_by_amount(mode=large, min=50000) | ≥5万 high；按笔数升 severity |
| 整数金额 | 异常整数金额（尾随≥4个0） | query_by_amount(mode=round) | 集中出现 medium；偶发 low |
| 重复对手方 | 同一对手方高频往来（≥3笔） | query_by_counterparty(min_count=3) | ≥10笔 high；3-9 medium |
| 短间隔簇 | 同对手方短时密集（≤30min≥2笔） | query_burst(window_minutes=30, min_count=2) | 簇数≥3 high |

阈值规避/同日同额/快进快出 **MVP 不预冻**，留作沉淀示例或后续加。

---

## 五、两个 Agent

| | 维度 agent | 追问 agent |
|---|---|---|
| output_type | `DimensionFinding`（结构体） | `str` |
| 工具 | 只读 Toolset（5 个） | 只读 Toolset + `query_findings` + `create_dimension` |
| instructions | 动态：每次跑用该维度 prompt | 静态：通用 QA + 多轮 |
| 工具循环 | agentic 单次 run 内多步（自己调 N 次工具直到满意） | 有 |
| 多轮对话 | ❌ 不跨 analyze 记 | ✅ message_history 持久化 |
| 阶段卡 | STAGE_AI_ANALYSIS | STAGE_AI_QA |

- `agent_factory.get_agent` 现有缓存 key 含 instructions → 每个维度 prompt 各自一个
  缓存 agent 单例（conventions「模块级单例」天然成立）。
- 防失控：`retries={'tools':N,'output':N}` + `UsageLimits(tool_calls_limit=...)`。

### `DimensionFinding` output_type（Q1）
```python
class DimensionFinding(BaseModel):
    type: str
    severity: Literal["high","medium","low"]
    counterparty: str | None = None
    amount: str | None = None          # 合计金额
    detail_text: str                    # 自然语言分析 = 右侧详情正文
    evidence_record_ids: list[int]      # 命中 flow_record id
    confidence: float                   # 0-1
```
一次维度运行产出**一条聚合 finding**（Q2）；零命中 → 不建 finding，summary 记 task.config。

---

## 六、`create_dimension` 沉淀工具（追问 agent 持有）

```python
@agent.tool
async def create_dimension(ctx, *, name, purpose, steps, judgment, severity):
    """沉淀新审查维度。字段缺一拒绝。
    Args:
      name: 维度名（≤20字）
      purpose: 要查什么异常（1-2句）
      steps: 按序列出要调哪些工具、传什么参数（list[{tool,params}]，tool 限白名单）
      judgment: 命中/severity 判定标准
      severity: high|medium|low
    """
```
- 服务端用固定模板拼 `prompt` 写库。`steps.tool` 限只读工具白名单，编造 → `ModelRetry`。
- 落库 `source="agent"`、`enabled=false`（**草稿**，需人在维度管理页启用才进 analyze）。
- **agent 没有删除工具**——删维度全在 UI/后端做。

---

## 七、权限与生命周期

**维度删除（UI/后端，非 agent）**：
- `source=system`：仅 admin 可删。
- `source=agent`：owner(`created_by`)/admin 可删。

**重跑策略（Q5）**：`POST /analyze` 前**只删 `status='pending'` 的 finding**，保留
`accepted`/`ignored` 人工结论（呼应"清洗不删减"硬底线）。新 finding 默认 pending。
已忽略维度重跑命中 → 生成新 pending（不偷偷复活旧 ignored）。

**会话删除（Q9）**：删会话只删对话历史，**不影响已沉淀维度**（沉淀是 create_dimension
产物，落 `audit_dimensions`，跟会话独立）。

---

## 八、数据模型（additive Alembic 迁移）

**新增 `AuditDimension`**（复刻 KeywordCard）：
```
id, name(str), source(str: system|agent), purpose(text),
steps(jsonb list[{tool,params}]), judgment(text), severity(str),
prompt(text 服务端拼好的成品缓存), enabled(bool default true),
created_by(int FK users.id nullable), created_at, updated_at
```
- `source=system` 5 条由迁移 seed；`source=agent` 来自 create_dimension（默认 enabled=false）。

**新增 `AuditConversation`**（多会话，Q9）：
```
id, task_id(FK tasks.id), title(str 首问题前10字), 
message_history(jsonb), created_at, updated_at
```
`task.config.active_conversation_id` 存当前激活会话。

**`Finding` additive 加列**（不动现有字段）：
- `dimension_id` (FK audit_dimensions.id, nullable)
- `detail_text` (Text, nullable)
- `evidence_record_ids` (jsonb, nullable)
- `source` (str, nullable) —— `rule`(维度跑出) | 兼容历史占位

`migrations/env.py` 登记新模型（spec 必须项，否则 autogenerate 漏表）。

---

## 九、API

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/audit-dimensions` | 列维度（所有登录用户可读） |
| POST/PUT/DELETE | `/api/audit-dimensions[/{id}]` | 维度 CRUD（admin；删 system 需 admin，删 agent 建的需 owner/admin） |
| POST | `/tasks/{id}/analyze` | **改造**：异步 background task，串行跑 enabled 维度，WS 逐条推进度 |
| GET | `/tasks/{id}/findings` | 不变 |
| POST | `/tasks/{id}/analyze/chat` | **改造**：真追问 agent.run（多轮 + create_dimension） |
| GET/POST/DELETE | `/tasks/{id}/analyze/conversations[/{id}]` | 会话列表/新建/删除（Q9） |

---

## 十、前端改造（`tasks/$id/analyze.tsx`）

1. **控制条**：去「快速/深度」单选；保留「开始分析」黑底主按钮 + 上次分析时间。
2. **左侧**：「异常发现」→ 改名「**维度详情**」；finding 实时增量、按 severity 降序。
3. **右侧详情**：`detail_text` 替代占位 description；关联记录读 `evidence_record_ids`
   下钻；删 seeded 假时间分布 bar（或保留但读真实数据）。
4. **底部 `<ChatPanel>` → 悬浮球**（Q9）：
   - 收起态：右下 fixed 圆球（`bg-ink-900`）。
   - **hover 球**：扇形展开会话标题（第一个固定「＋新建会话」，后续 = 该会话首问题
     前 10 字，显示 `#N · 前10字`）。
   - 点标题进会话；点 ＋ 新建。
   - 展开态：面板（消息流 + 输入），切任务自动收起+清 echo。
   - **工具调用痕迹**：追问 agent 调只读工具时，AI 气泡小字显「🔍 已查询：…」。
   - **沉淀可视化**：agent 调 create_dimension 时，AI 气泡渲染「已沉淀维度：XXX（草稿，待启用）」。
5. 任务详情页内（非全局悬浮）。

---

## 十一、验收标准

- [ ] `POST /analyze` 异步串行跑 5 个 system 维度，产真实聚合 finding（含 detail_text），
      WS 逐条推进度，左侧实时增量。
- [ ] admin 能 CRUD 维度；启用/禁用后重跑，findings 集合变化。
- [ ] 重跑保留 accepted/ignored 人工结论，只重算 pending。
- [ ] 追问悬浮球：hover 扇形展开多会话标题；多轮追问有上下文；切任务隔离。
- [ ] 追问调只读工具时气泡显工具痕迹；调 create_dimension 显「已沉淀草稿」。
- [ ] create_dimension 限 steps.tool 白名单，编造触发重试；建出维度 enabled=false。
- [ ] 维度管理页启用沉淀维度后，下次 analyze 立即生效（零代码）。
- [ ] pydantic-ai conventions 全对齐（agent 单例 + deps + Toolset + message_history 往返）。
- [ ] `query_by_time` 默认剔 00:00:00；所有工具带 limit。
- [ ] 单测：5 个工具纯逻辑、create_dimension 白名单校验、维度 prompt 拼装、重跑保留策略。

## 十二、风险

| 风险 | 缓解 |
|---|---|
| 串行跑 5 维度慢（30s~1min） | 异步 background + WS 进度，用户可离开 |
| 单维度 agent.run 失败 | try/except 跳过该维度 + log，不阻塞其他（容错 spec） |
| agent 调工具爆 context | 所有工具 limit（默认200，硬上限1000） |
| create_dimension 写脏 prompt | 强类型 schema + 白名单 + 默认 enabled=false 人审 |
| 追问多会话 history 膨胀 | 独立 AuditConversation 表（不撑 task.config） |
| LLM 不可用 | analyze 跳过该维度降级；追问返错误提示，不崩流程 |
