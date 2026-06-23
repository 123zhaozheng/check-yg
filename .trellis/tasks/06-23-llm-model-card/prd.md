# LLM 模型卡片 + 参数可配化

## 背景

`06-23-web-4` 收尾时,日志诊断加厚后抓到画像生成失败的真实根因:

```
app.llm.portrait: 文档画像提取失败（将返回 None → hover 显示「画像待生成」）:
  document_name=BOC_new_133315.pdf, 异常类型=UnexpectedModelBehavior,
  异常=Model token limit (1500) exceeded before any response was generated.
  Increase the `max_tokens` model setting, or simplify the prompt...
```

根因:`step-3.7-flash` 是 reasoning 模型,**reasoning token 计入 `max_completion_tokens` 预算并按 output 计费**(research §3 已核实)。1500 预算被推理阶段烧光,没轮到输出结构化 tool_call,pydantic-ai 抛 `UnexpectedModelBehavior`。分类/标准化同理。

更深的接线缺失:**设置页早就有 `llm.max_tokens` 项(默认 2000),但三模块(classifier/portrait/normalizer)根本没读它**,各自用模块内硬编码常量(`_MAX_TOKENS_CLASSIFIER=1500` / portrait 1500 / normalizer 4000)。设置项是孤儿,改了不生效——这就是用户「为什么不能自定义在设置中」的答案。

用户诉求:把 LLM 参数(max_tokens / 推理预算 thinking / temperature / timeout)真正接到设置页可配,并引入「模型卡片」(显示名/上下文长度/最大输出/工具调用/推理模式/流式),未在库里时手动填写。参考 kimi-2.7 卡片形态(256K 上下文 / 32K 最大输出 / 工具调用 / 推理模式 / 流式)。

任务目录:`.trellis/tasks/06-23-llm-model-card`
分支:沿用 `feat/web-split`
研究依据:`.trellis/tasks/06-23-web-4/research/llm-model-card-and-gateway.md`

## 硬底线(沿用全项目)

- 前端 Chrome 96/108 正常渲染,单色设计(9 级 ink token,错误黑白不用红色)。
- 清洗「不删减」:本任务不动 flow_records 保留语义,只动 LLM 调用参数与模型卡片配置。
- 不污染 main 分支。
- pydantic-ai 提示词保真(不动 SYSTEM_PROMPT_*)。
- LLM 兼容性(modelscope tool_choice:required 空壳)不在本任务范围(research §6.2 仅供后续参考)。

## 决策(已 grill 确认)

1. **存储形态**:独立 `llm_models` 表 + CRUD(支持多模型卡片管理)。**按阶段选模型**:独立 `llm_model_assignments` 表(stage 枚举 → model_id),分类/画像/标准化/AI分析/问答/报告 各阶段可指定不同卡片。
2. **reasoning 控制**:纳入。模型卡片记 `is_reasoning` 布尔,设置页暴露 `default_thinking` 预算档位(off/low/medium/high,reasoning 模型默认 low)。
3. **粒度**:单个新任务打包做。
4. **api_key 存储**:卡片存明文 api_key,API 返回脱敏(只返 `********` 后 4 位)。
5. **旧设置项**:保留作兜底。选了阶段卡片后从卡片读;未选/卡片被删时回退 `llm.*` 设置项 + 模块兜底常量。兼容现有部署。
6. **前端位置**:设置页「集成与模型」tab(原「渠道与解析」扩展或重命名),管理模型卡片 + 每阶段选卡片。
7. **鉴权**:模型卡片 CRUD + activate 限 admin;列表 `GET /api/llm-models` 所有登录用户可读。
8. **阶段范围**:`classification` / `portrait` / `normalization`(已接 LLM,真实生效)+ `ai_analysis` / `ai_qa` / `report_generation`(预留映射位,等后续接真实 LLM 时生效;当前 analysis.py / report_chapter_builder 是占位)。

## 实现项

### ① 新增 `llm_models` + `llm_model_assignments` 表 + Alembic 迁移

- `backend/app/models/llm_model.py` 新模型 `LLMModel`:
  - `id` / `display_name`(显示名,如「kimi-2.7」)/ `model_name`(实际 model id)/ `provider_base_url` / `api_key`(明文存,API 脱敏)/ `context_length`(int)/ `max_output`(int)/ `supports_tool_call`(bool)/ `supports_tool_choice_required`(bool)/ `is_reasoning`(bool)/ `supports_streaming`(bool)/ `default_thinking`(枚举 off/low/medium/high,非 reasoning 模型为 off)/ `default_max_tokens`(int)/ `default_temperature`(float,可空,空则回退 llm.temperature)/ `created_at` / `updated_at`。
  - 不设 `is_active` 全局布尔(改用 assignments 按阶段选)。
- `backend/app/models/llm_model_assignment.py` 新模型 `LLMModelAssignment`:
  - `id` / `stage`(枚举 `classification`/`portrait`/`normalization`/`ai_analysis`/`ai_qa`/`report_generation`,unique)/ `llm_model_id`(FK→llm_models.id,nullable——nullable 表示该阶段未指派,回退兜底)/ `created_at` / `updated_at`。
  - 每个 stage 至多一行(unique stage)。
- Alembic 迁移:down_revision = `c4a1e9f8b2d7`(06-23-web-4 的 head),create 两张表。database.py sqlite 路径:新表由 create_all 覆盖(已有模型),无需额外 ALTER。
- **seed 默认卡片**:迁移后 seed 几张常见模型卡片(research §5):step-3.7-flash(`is_reasoning=true`/`default_thinking=low`/`default_max_tokens=6000`)/ deepseek-chat(`is_reasoning=false`/`default_max_tokens=4000`)/ qwen-plus / kimi-k2.6。**seed 默认 assignments**:给 classification/portrait/normalization 三阶段默认指派 step-3.7-flash(若已 seed)。seed 值 caveat:kimi 32K 最大输出未独立核实,seed 时按已知写,描述里标「待核实」。

### ② 三模块按阶段读模型卡片参数(接线修复)

- 新增 `backend/app/services/llm_model_service.py`:
  - `get_stage_model(db, stage) -> LLMModel | None`:查 `llm_model_assignments` 该 stage 指派的卡片;未指派或卡片被删返 None。
  - 解析顺序:**阶段卡片 > runtime `llm.*` 设置项 > 模块硬编码兜底常量**。
- `extractor.py:__init__` 接收 `stage_models: dict[stage, LLMModel | None]`(由 runner 从 DB 查好传入,避免 extractor 内直接访问 DB)。构造 classifier/normalizer/portrait_extractor 时,各按自己的阶段(`classification`/`normalization`/`portrait`)取卡片,传:
  - `max_tokens` = 卡片 `default_max_tokens`(无卡片时回退 runtime `llm.max_tokens` 再回退模块常量)。
  - `thinking` = 卡片 `default_thinking`(reasoning 模型传 low/medium/high;非 reasoning 或 off 时不传)。
  - `api_url`/`api_key`/`model` = 卡片值(无卡片回退 runtime `llm.*`)。
  - `temperature` = 卡片 `default_temperature`(空则回退 runtime `llm.temperature`)。
  - `timeout` 仍从 runtime settings 读。
- `runner.py`:启动任务时从 DB 查 `classification`/`portrait`/`normalization` 三阶段的卡片,传给 extractor。
- `agent_factory._build_agent` / `get_agent`:加 `thinking` 参数,透传到 `ModelSettings(thinking=...)`(pydantic-ai 1.107.0 支持,research §1)。`thinking='off'`/`None`/非 reasoning 时不传该字段(避免给非 reasoning 模型发 reasoning_effort 报错)。
- `thinking` 计入 agent 缓存 key(同 max_tokens)。
- 模块硬编码 `_MAX_TOKENS_*` 常量保留为兜底默认,不删。
- analysis.py(AI 分析/问答占位)+ report_chapter_builder(报告占位):本任务只确保它们**能**按 `ai_analysis`/`ai_qa`/`report_generation` 阶段读卡片(预留接线函数),但因其当前是占位不调真实 LLM,本任务不强制接通真实调用——等后续任务接 LLM 时生效。

### ③ runtime settings 兼容(旧设置项保留作兜底)

- `llm.base_url`/`llm.api_key`/`llm.model_name`/`llm.max_tokens`/`llm.temperature` 设置项全部保留,语义统一为「阶段未指派卡片时的兜底」。
- 解析优先级见 ②:阶段卡片 > runtime settings > 模块兜底常量。
- 现有 `llm.max_tokens` 默认值从 2000 调整为更合理的兜底(如 4096,防 reasoning 模型兜底时也烧光)——或保持 2000 不动,由用户在卡片里配。grill 决定(见待 grill)。

### ④ 后端 API:模型卡片 CRUD + 阶段指派

- `backend/app/routers/llm_models.py`(新):
  - `GET /api/llm-models` 列表(所有登录用户可读,api_key 脱敏返 `********XXXX`)。
  - `POST /api/llm-models` 新建(admin)。
  - `PUT /api/llm-models/{id}` 更新(admin;api_key 字段为空/脱敏串时保持原值不变)。
  - `DELETE /api/llm-models/{id}` 删除(admin;若该卡片被某阶段指派,先解除指派或拒绝删除——见待 grill)。
- `backend/app/routers/llm_model_assignments.py`(新,或合并进上一个 router):
  - `GET /api/llm-model-assignments` 列出 6 个阶段 + 各自指派的卡片(所有登录用户可读)。
  - `PUT /api/llm-model-assignments/{stage}` 指派/解除该阶段的卡片(body: `{llm_model_id: int | null}`,admin)。
- 鉴权:CRUD/指派限 admin;列表所有登录用户可读。沿用现有 `require_admin` 依赖(若无则按现有 settings 路由的鉴权模式)。
- `LLMModelResponse` schema:api_key 字段返脱敏串(如 `********XXXX`),不返明文。

### ⑤ 前端:设置页「集成与模型」tab

- `frontend/src/routes/__authenticated/settings.tsx`:现有「渠道与解析」tab 扩展或重命名为「集成与模型」,内含两块:
  - **模型卡片管理**:卡片列表 table(显示名 / model_name / 上下文 / 最大输出 / 工具调用 / 推理模式 / 流式 / default_max_tokens / default_thinking)+ 新建/编辑/删除。api_key 字段编辑时显示脱敏占位,留空表示不改。
  - **阶段模型指派**:6 个阶段(classification 分类 / portrait 画像 / normalization 标准化 / ai_analysis AI分析 / ai_qa AI问答 / report_generation 报告生成)各一个下拉,选卡片或「未指派(用兜底)」。未接 LLM 的阶段(ai_analysis/ai_qa/report_generation)标注「预留,待接入」。
- 单色设计,Chrome 96/108 兼容,不引 radix。
- `lib/api.ts` 加 `LLMModel` / `LLMModelAssignment` / `Stage` 类型 + CRUD + 指派方法;`hooks/use-llm-models.ts`(新)。

### ⑥ 测试

- 后端 pytest:模型卡片 CRUD(5,含 api_key 脱敏 + 留空不改)+ 阶段指派 GET/PUT(2)+ 三模块按阶段从卡片读 max_tokens/thinking 接线(mock,断言传入 ModelSettings 含卡片值,未指派时回退兜底)(3)+ seed 默认卡片+assignments(1)+ admin 鉴权拒绝 auditor 改(1)。
- 前端 build 通过(chrome108)。

## 验收

1. 设置页「集成与模型」能新建/编辑/删除模型卡片,字段齐全(显示名/上下文/最大输出/工具调用/推理模式/流式/default_max_tokens/default_thinking);能按 6 阶段各指派一张卡片或「未指派」。
2. 给 portrait 阶段指派一张 step-3.7-flash 卡片(`default_max_tokens=6000`、`is_reasoning=true`、`default_thinking=low`),跑任务:控制台**不再**出现 `UnexpectedModelBehavior: Model token limit exceeded`;画像生成成功(或至少不是 token 烧光),hover 显示画像内容。
3. 三模块实际用的 max_tokens/thinking = 阶段指派卡片值(日志或断言可见);未指派阶段回退 runtime settings + 模块兜底常量,不崩。
4. api_key 在 API 返回和前端均为脱敏,编辑留空不改原值。
5. 164 现有测试不破 + 新测试通过 + 前端 build 通过。

## 实现顺序建议

1. ① 模型表 + 迁移 + seed(后端基础)
2. ② 三模块接线(核心止血:解决 token 烧光)
3. ③ runtime settings 兼容
4. ④ CRUD API
5. ⑤ 前端模型管理
6. ⑥ 测试

② 是核心,可以先做让画像跑通,再做完整 CRUD/前端。

## 不做(范围外)

- modelscope `tool_choice:"required"` 空壳兼容(research §6.2,后续任务)。
- pydantic-ai 内置模型库(1.107.0 没有,无法用)。
- 把 `max_tokens` 映射成旧版 `max_tokens`(pydantic-ai 硬映射,本任务用调大 + thinking=low 解决,不走 extra_body 绕)。
- LLM 网关/代理(用户提到的 pydantic-ai gateway 是托管产品,不引入)。
- analysis.py / report_chapter_builder 接真实 LLM 调用(本任务只预留阶段映射位,等后续任务接通真实 agent.run)。
- 同一阶段多模型负载均衡/故障切换(本任务每阶段单卡片)。

## 决策(剩余小决策,已 grill 确认)

- **删除被指派的卡片**:拒绝删除,API 返 409 提示「该卡片被某阶段指派,请先解除指派再删除」。
- **`llm.max_tokens` 兜底默认值**:调到 16000(防 reasoning 模型未指派卡片兜底时也烧光 token)。
- **seed 默认 assignments**:seed 只建卡片,`llm_model_assignments` 全空;用户在设置页手动给每阶段选卡片。首次跑任务前需先配,或直接靠 16000 兜底先跑通。
