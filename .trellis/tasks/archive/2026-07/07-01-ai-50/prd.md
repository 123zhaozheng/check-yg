# 关键词库 AI 生成按钮（备注+名称→50关键词）

## Goal

在「关键词库」页「新建关键词卡片」对话框中，给「备注」字段旁加一个类 Gemini
sparkle 图标的 AI 生成按钮。当用户已填卡片名称 + 备注、且关键词列表为空时，点
击该按钮调用后端 AI（pydantic-ai agent）一键生成约 50 个符合「卡片名 + 备注」
语义的关键词，填入可编辑的关键词列表（用户仍可在保存前增删改）。

**为什么**：关键词库是流水审查的命中资产，目前 admin 只能逐个手敲或 excel 导入。
对「高/中/低」风险卡片，给出名称+备注后由 AI 批量发散同义/变体/相关词，大幅降
低建库成本，是项目已有 AI 能力（normalizer/classifier/analysis/report）的自然
延伸。

## What I already know（代码调研结论）

### 前端 `frontend/src/routes/__authenticated/keyword-library.tsx`
- `KeywordCardDialog`（mode="create"）字段：卡片名称 `name` / 风险等级
  `riskLevel`（高/中/低 select）/ 备注 `note`（Input，placeholder「可选」）/ 关键
  词列表 `terms`（动态增删 Input 行，create 模式专属）。
- `terms` 初始态 `[""]`（一行空输入）；「关键词列表为空」= 所有行 trim 后均空。
- 新建/编辑/删除/导入 均限 admin（`useCurrentUser role===admin`）。
- 另有 `KeywordTermsDialog`（点卡片名打开，管理**已存在**卡片的关键词列表，
  PUT 全量替换 terms）—— 同样有可增删的 terms 列表，词为空时提示录入。
- 设计系统：**单色 ink tokens，无 radix，无彩色**；图标用 lucide-react（已有
  `Download`/`Upload`）；命中高亮只用粗体/下划线。
- hooks 在 `frontend/src/hooks/use-keyword-library.ts`（react-query mutation，
  invalidate `KEYWORD_LIBRARY_QUERY_KEY`）。

### 后端 `backend/app/routers/keyword_library.py` + service
- `POST /api/keyword-library/cards` — 新建卡片（admin），body `name/risk_level/
  note + terms[]`，terms 去重保序。
- 鉴权统一走 `check_admin_permission(db, user)`。
- service `_dedup_terms` 去重保序可直接复用。

### LLM 基础设施（成熟，直接复用）
- pydantic-ai v1.107.0，约定见 `docs/research/pydantic-ai-conventions.md`。
- `backend/app/llm/agent_factory.py::get_agent()` —— 模块级单例，按
  (base_url,api_key,model,timeout,max_tokens,thinking,temperature,
  output_type,instructions,deps_type) 缓存。
- 范式：`output_type=<pydantic BaseModel>` + `instructions=<系统提示词>` +
  可选 `deps_type` + 可选 `toolsets`；`agent.run(user_prompt) → result.output`。
- `analysis.py::_resolve_agent_params(model, fallback_max_tokens=)` —— 阶段
  卡片 > env settings 优先级解析（卡片字段空回退 env）。
- 阶段卡片：`get_stage_model(db, STAGE_*)`；现有阶段 classification/portrait/
  normalization/ai_analysis/ai_qa/report_generation（`llm_model_assignment.py`）。
- 结构化输出范例：`normalizer.py`（`NormalizedRows` + `output_validator` 兜底
  铁规则，失败抛 `ModelRetry`）；`types.py` 放 output_type 模型。
- env settings：`LLM_API_ENDPOINT` / `LLM_API_KEY` / `LLM_MODEL_NAME` /
  `LLM_TIMEOUT`（默认 ollama 本地 qwen2.5:7b）。

### 前端 API 层 `frontend/src/lib/api.ts`
- 关键词库类型 + 调用函数在 1174–1318 行（`KeywordRiskLevel` /
  `KeywordCardUpsertBody` / `createKeywordCard` 等），追加一个 generate 函数即可。
- `api.post<T>(path, body)` 标准 JSON 调用。

## Assumptions（待验证）

- AI 生成走后端新端点 `POST /api/keyword-library/generate-terms`（admin），入参
  `name/risk_level/note`，出参 `terms: string[]`。**不在前端直连 LLM**（key 不外
  泄、复用阶段卡片、与项目所有 AI 一致）。
- 新增阶段 `keyword_generation`（`llm_model_assignment.py` + api.ts 类型 + settings
  标签），走 `get_stage_model(db, STAGE_KEYWORD_GENERATION)` → `_resolve_agent_params`
  解析 → `get_agent(KeywordTerms, instructions, ...)`。未指派时回退 env 兜底。
- 复用 pydantic-ai agent，`output_type` 为「关键词列表」容器（`{terms: list[str]}`），
  instructions 硬编码领域（银行/支付流水审查命中用关键词）+ 数量约束。
- 生成结果**只填入前端编辑态 terms**，不自动落库；用户仍需点「保存」才建卡（与
  现有手敲流程一致，AI 只是把空列表填满）。
- 按钮只在 create 模式出现（用户明确说「新建关键词库」）；KeywordTermsDialog 不加
  （Q1 已确认只做新建）。

## Open Questions

## Requirements（evolving）

- **阶段模型**：新增 `keyword_generation` 阶段（`llm_model_assignment.py` + `api.ts`
  类型 + `settings.tsx` 标签），设置页自动多一行下拉。未指派时回退 env 兜底。
- **前端 UI**：「新建关键词卡片」dialog（create 模式）备注字段右侧出现 AI 生成按钮
  （lucide `Sparkles` 图标，单色）。只在该 dialog 出现（Q1 已确认）。
- **触发条件**：`name` 非空 **且** `note` 非空 **且** terms 全空 —— 按钮可点击；否则
  禁用/置灰，hover 提示原因。
- **调用链**：点击 → `POST /api/keyword-library/generate-terms`（admin）→ 后端用
  `get_stage_model(db, STAGE_KEYWORD_GENERATION)` 取卡片 → `_resolve_agent_params`
  解析 → `get_agent(KeywordTerms, instructions, ...)` → agent.run → 返回 `terms[]`。
- **结果应用**：返回关键词列表 → 去重后填入 terms 编辑态（替换当前空行）。生成结果**只填表单态，不自动落库**；用户仍需点「保存」才建卡。
- **生成后自动去重**：后端（或前端）对 AI 返回的 terms 去重（保留顺序），避免 LLM 自己重复输出。复用或对齐 service._dedup_terms 逻辑。
- **失败安全**：生成失败（LLM 错误、超时、返回过少等）时，**不改动**用户已手敲的 terms（当前为空时就是保持空）。只在成功且有内容时才替换空列表。
- **生成中 UX**：AI 按钮自己显示 loading（spinner）、禁用，不可重复点（Q5 已确认）。dialog 其他部分仍可操作（取消、改名/风险等级）。
- **失败处理**：LLM 不可用 / 超时 / 解析失败时给明确中文提示（toast 或 dialog 内
  错误文案），不影响 dialog 其他操作。
- **权限**：admin 专属（非 admin 看不到新建 dialog，天然满足）。
- **数量**：默认生成 50 个（Q4 已确认固定）。
- **非空时行为**：关键词列表已有内容时按钮禁用 + tooltip 说明「清空关键词列表后可使用 AI 生成」（Q2 已确认）。

## Acceptance Criteria（evolving）

- [ ] 设置页「集成与模型」Tab 出现「关键词生成」阶段下拉（未指派时显示「用兜底」）。
- [ ] 生成失败（LLM 错误/超时/返回过少等）时，不改动用户已手敲的 terms（当前为空则保持空）。
- [ ] LLM 返回的关键词列表在后端/前端去重（保留顺序），避免重复词进入表单。
- [ ] 关键词列表已有内容时，AI 按钮禁用 + tooltip 显示「清空关键词列表后可使用 AI 生成」。
- [ ] LLM 不可用时前端给出可读错误，dialog 不崩。
- [ ] 后端单测覆盖：agent 输出解析、去重保序、空 name/note 拒绝、阶段卡片未指派
  回退 env 兜底。

## Definition of Done

- 后端新增 agent + endpoint + 单测；lint/typecheck/CI 绿。
- 前端新增按钮 + hook + 集成；单色风格一致。
- 行为变更无需特别文档（dialog 内自解释）。

## Out of Scope（explicit）

- 不改现有 CRUD / 导入导出逻辑。
- 不做关键词质量评分 / 自动去重跨卡片。
- 不做流式输出（MVP 一次性返回）。
- （待 Q1 确认）KeywordTermsDialog 是否纳入。

## Technical Notes

- 复用 `agent_factory.get_agent`；output_type 放 `backend/app/llm/types.py`。
- endpoint 仿 `create_keyword_card` 鉴权与异常风格（admin + ValueError→422）。
- 前端 hook 仿 `useCreateKeywordCard`（mutation，但**不 invalidate**——结果填表
  单态，不落库不刷列表）。
- 提示词领域：银行/支付流水审查，命中对象为 counterparty_name / summary 文本，
  风险等级影响词风（高风险→敏感/违规主体，中低→常规异常）。
- 阶段常量：`STAGE_KEYWORD_GENERATION = "keyword_generation"`，加进 `STAGES` 元组
  （`llm_model_assignment.py`）。
- 前端类型：`api.ts` 的 `Stage` 联合加 `"keyword_generation"`；`settings.tsx` 的
  `STAGE_LABELS` 数组加 `{ stage: "keyword_generation", label: "关键词生成" }`。
- 无 DB 迁移（阶段指派表已有 stage 字符串列）。
- 参考范例：`report_agent.py`（阶段卡片接线 + `_resolve_agent_params`）；
  `normalizer.py`（结构化输出 + output_validator）。
