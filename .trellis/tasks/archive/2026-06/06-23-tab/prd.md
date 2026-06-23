# 06-23-tab 关键词库 + 关键词审查阶段 + 删概览 + 清洗规则折叠

## 背景

用户要三件事:
1. **全局关键词库** + 在「清洗标准化」与「AI 分析」之间插入「关键词审查」阶段。
2. 删任务详情的「概览」子 tab(用户口误称"概率 tab")。
3. 清洗页「应用规则」左侧栏改可折叠 + 默认收起。

## 范围(三块,单一任务)

### A. 全局关键词库(新增左侧导航页 + 后端 CRUD/导入)

**作用域**:全局共享资产,平行于「审查任务 / 设置」。左侧导航 `app-shell.tsx` 的 `NAV_ITEMS` 在 `/tasks` 与 `/settings` 之间插入 `{ to: "/keyword-library", label: "关键词库", icon: <Library/Tags> }`。

**数据模型(两表)**:
- `keyword_cards`: `id` / `name`(卡片名) / `risk_level`(高/中/低,卡片级) / `note`(备注,可空) / `created_at` / `updated_at`。词级**无**风险等级。
- `keyword_terms`: `id` / `card_id`(FK → keyword_cards.id, ondelete CASCADE) / `term`(关键词) / `created_at`。唯一约束 `(card_id, term)`。

**Alembic 迁移**:新建迁移,down_revision = 当前 head(`a5b2c0d3e1f8`,即 06-23-llm-model-card 的 head;实现前用 `alembic heads` 核实当前 head)。建两表 + 唯一约束。不 seed 数据(用户自己导入/建)。

**后端 API**(新 router `routers/keyword_library.py`,prefix `/api`):
- `GET /api/keyword-library/cards` — 列出卡片(含每卡 term 数、风险等级)。所有登录用户可读。
- `POST /api/keyword-library/cards` — 新建卡片(admin)。body: name/risk_level/note + terms[]。
- `PUT /api/keyword-library/cards/{id}` — 编辑(admin)。name/risk_level/note 可改;terms 全量替换。
- `DELETE /api/keyword-library/cards/{id}` — 删卡(admin,级联删 terms)。若该卡已被任务审查引用(keyword_hits 有引用),**拒绝删除返 409**,提示先解除关联(对齐 LLM 模型卡删已指派返 409 的模式)。
- `POST /api/keyword-library/import` — excel 导入(admin)。multipart 文件。**合并追加去重**:同名卡片存在则把新 term 追加进旧卡(已有 term 跳过),risk_level/note 用 excel 新值覆盖;同名卡片不存在则新建。返回导入统计(新建卡片数/追加卡片数/新增词数/跳过重复词数)。
- `GET /api/keyword-library/export` — excel 导出(所有登录用户可读,便于分发规范模板)。返 xlsx 流,表头 `卡片名称,关键词,风险等级,备注`,一行一词,卡片名连续多行。
- `GET /api/keyword-library/cards/{id}` — 卡片详情(含 terms 列表)。

**excel 导入规范**:表头 `卡片名称,关键词,风险等级,备注`。一行一个关键词。卡片名称相同的行合并为同一张卡(风险等级/备注取该卡片名分组首行非空值)。风险等级合法值:高/中/低(非法值→该行报错或兜底为"中",实现时取「跳过该行并记入导入统计的 rejected 行」)。

**权限**:CRUD/导入限 admin,列表/导出/详情所有登录用户可读。对齐 LLM 模型卡模式——参照 `backend/app/routers/llm_models.py` 与 `backend/app/schemas/llm_model.py` 的 admin gating 写法。

**前端**(新 route `frontend/src/routes/__authenticated/keyword-library.tsx`):
- 卡片表格:卡片名 / 词数 / 风险等级 / 备注 / 操作(编辑/删除)。
- 顶部:「导入 excel」(上传 dialog) + 「导出 excel」 + 「新建卡片」(admin 可见)。
- 新建/编辑 dialog:卡片名 + 风险等级(高/中/低 select)+ 备注 + 关键词列表(可增删的 term 输入行)。
- 导入 dialog:文件选择 + 上传 + 导入结果统计展示。
- 单色 ink tokens,无 radix,admin gating(参照 `settings.tsx` 集成与模型 tab 的 admin 判断 `useCurrentUser`)。

### B. 关键词审查(任务详情新子 tab + 后端匹配引擎)

**前端 tab 插入**(`$id.tsx`):TABS 在 clean 与 analyze 之间插 `{ segment: "keyword-review", label: "关键词审查" }`。STAGES 从 4 段(导入/清洗/分析/报告)更新为 5 段(导入/清洗/关键词/分析/报告)。新 route `frontend/src/routes/__authenticated/tasks/$id/keyword-review.tsx`。

**匹配引擎**:移植 legacy `src/core/matcher.py` 的 `NameMatcher` 三层逻辑到 `backend/app/services/keyword/matcher.py`:
- 精确匹配(`in` 子串,置信度 100)。
- 脱敏匹配(正则 `张*`/`赵*辰`/`欧**辰` 模式,置信度 90)。
- 模糊匹配(Levenshtein ratio,阈值默认 70%,置信度 = ratio*100)。
- 优先级:精确 > 脱敏 > 模糊,返首个命中。
- 把 `customer_name` 参数语义换成 `keyword`(被匹配文本仍是流水字段值)。`MatchResult` 字段名相应改 `keyword`/`matched_text`/`match_type`/`confidence`/`position`。

**依赖**:装 `python-Levenshtein`(模糊层)。实现前先 `uv pip install python-Levenshtein` 验证 Windows 预编译轮子可用;若装不上,fallback 用标准库 `difflib.SequenceMatcher`(实现时记一条 log 说明降级)。模糊层用 `Levenshtein.ratio`。

**匹配对象**:清洗后 `flow_records` 中 `record_type='standard'` 的记录,**只扫 `counterparty_name` + `summary` 两列**(拼成待匹配文本)。不扫 excluded/unparsed。

**触发与重跑**:`POST /api/tasks/{task_id}/keyword-review/run` — body: `card_ids: int[]`(用户多选的卡片)。后端:
1. 取这些 card 的所有 term(展开成 keyword 列表)。
2. 取该 task 所有 standard flow_records。
3. 逐行 × 逐词跑三层匹配,命中即记。
4. **重跑策略(简单)**:先 `DELETE FROM keyword_hits WHERE task_id=?`,再插新命中(同 task 可换卡片反复重审,结果即当前选中卡片集)。
5. 返回统计(扫描记录数 / 命中记录数 / 命中词数 / 高风险命中数)。

**命中表 `keyword_hits`**:
- `id` / `task_id`(FK) / `flow_record_id`(FK → flow_records, 不级联,行被捞回改 type 时命中是否失效见下) / `keyword_card_id`(FK, ondelete SET NULL?或 RESTRICT——见删卡 409 逻辑,倾向 RESTRICT 即删卡前必须无命中) / `keyword_term_id`(FK) / `match_type`(精确/脱敏/模糊) / `confidence`(int 0-100) / `risk_level`(高/中/低,来自卡片) / `matched_field`(counterparty_name / summary) / `matched_snippet`(命中片段文本) / `status`(pending/confirmed/ignored,默认 pending) / `note`(可空) / `created_at` / `updated_at`。
- 删卡片时若该卡有命中 → 409(对齐删已指派模型卡)。

**命中人工处理 API**:
- `GET /api/tasks/{task_id}/keyword-review/hits` — 分页列命中(支持按 status/risk_level/match_type 过滤)。
- `PATCH /api/tasks/{task_id}/keyword-review/hits/{hit_id}` — 改 status/note(采纳/忽略/备注)。

**关键边界(实现时确认)**:standard 行被「捞回」改 record_type 后,其历史 keyword_hit 如何处理?本次取**简单策略**:keyword_hit 不级联清理,但 `GET hits` 时 join flow_records 仅展示仍为 standard 的行的命中(捞回变成 excluded/unparsed 的行的命中在列表中过滤掉,但记录保留以便重跑覆盖)。或更简单:捞回不触发改命中,下次重跑自然按当前 standard 重算。倾向后者——重跑才同步,避免捞回时额外清理逻辑。prd 记此决策,实现时按"重跑才同步"。

**前端审查页**(`keyword-review.tsx`,单色对齐清洗/分析页):
- 顶部控制条:「选择关键词卡片」(多选,从全局 keyword-library 拉 card 列表,checkbox)+「开始审查」黑底主按钮。展示上次审查时间。
- 4 KPI:扫描记录数 / 命中记录数 / 命中关键词数 / 高风险命中数。
- 命中表格:流水行(日期/对手/金额/摘要)+ 命中卡片名 + 关键词 + 匹配类型 + 置信度 + 风险等级 + 命中字段 + 命中片段(片段里高亮命中词,单色用粗体/下划线不用彩色) + 操作(采纳为告警/忽略/备注)。
- 状态过滤:全部/待处理/已采纳/已忽略。

**不自动喂 AI 分析**:keyword_hits 独立,AI 分析页 placeholder 逻辑不动。后续如要把命中转 AI findings 另起任务。

### C. 删概览 + 清洗规则折叠(小改)

**删概览**(`$id.tsx` + `$id/index.tsx`):
- `$id.tsx` TABS 删 `{ segment: "overview", label: "概览" }`。
- `$id/index.tsx` redirect 从 `/tasks/$id/overview` 改为 `/tasks/$id/import`。
- 删 `frontend/src/routes/__authenticated/tasks/$id/overview.tsx`(若仅概览用)。

**清洗规则折叠**(`clean.tsx`):
- 左侧「应用规则」aside(`clean.tsx:208-243`)加折叠态:`useState` 控制 `rulesCollapsed`,默认 `true`(收起)。收起时只显示一个「应用规则 ▸」按钮(或窄条),展开时恢复现有规则列表。展开/收起用 `ChevronRight`/`ChevronDown` 图标(已 import)。
- 收起后右侧表格区拓宽(aside 宽度变 0 或窄条)。

## 验收标准(AC)

1. 左侧导航出现「关键词库」,点开是全局卡片管理页;admin 能新建/编辑/删除卡片、导入/导出 excel;非 admin 能看列表/导出但不能改。
2. excel 导入:同名卡片合并追加去重,新词加入、重复词跳过、风险/备注新值覆盖;导入返统计。
3. 任务详情 tab 顺序:数据导入 → 清洗标准化 → 关键词审查 → AI 分析 → 审查报告 → 导出;「概览」已删;`/tasks/:id` 落到「数据导入」;顶部进度条 5 段含「关键词」。
4. 关键词审查页能多选卡片 → 开始审查 → 命中表展示;重跑清旧命中再算;命中可采纳/忽略/备注。
5. 匹配只作用于 standard 记录的对手名+摘要;三层(精确/脱敏/模糊 70%)按优先级返首个命中。
6. 清洗页「应用规则」默认收起,可点开。
7. 后端测试:keyword_library CRUD/导入/权限 + keyword-review run/hits/PATCH + matcher 三层单测(覆盖精确/脱敏/模糊/优先级/阈值)。`cd backend && .venv/Scripts/python.exe -m pytest tests/ -x` 全过。
8. `alembic heads` 单 head;`cd frontend && pnpm build` 通过(chrome108 target,无 radix)。

## 代码参照(implement 阶段子 agent 必读)

- **三层匹配引擎源**:legacy `src/core/matcher.py`(`NameMatcher` / `MatchType` / `MatchResult` / `generate_desensitized_patterns` / `match_exact` / `match_desensitized` / `match_fuzzy` / `match`)。
- **CRUD + 权限 + 删已引用返 409 模板**:`backend/app/routers/llm_models.py` + `backend/app/schemas/llm_model.py` + `backend/app/models/llm_model.py`(06-23-llm-model-card,已归档但代码在)。
- **前端 admin gating + dialog + 单色 tab 模板**:`frontend/src/routes/__authenticated/settings.tsx`(集成与模型 tab)+ `frontend/src/hooks/use-llm-models.ts`(query/mutation 模式)。
- **前端任务 tab 结构**:`frontend/src/routes/__authenticated/tasks/$id.tsx`(TABS/STAGES)。
- **清洗页折叠改造点**:`frontend/src/routes/__authenticated/tasks/$id/clean.tsx:208-243`(应用规则 aside)。
- **后端 task router 现有端点模式**:`backend/app/routers/tasks.py`(cleaning/commit、analyze 端点的路径与权限写法)。
- **review_service 现有匹配相关**:`backend/app/services/review_service.py`(如存在客户名匹配,可参考其与 flow_records 的查询模式)。

## 显式不做

- 同义词/排除词(卡片只 = 卡片名+风险等级+备注,词只 = 关键词)。
- 关键词审查命中自动喂 AI 分析(独立命中表,AI 分析逻辑不动)。
- 关键词库的批量操作/分组/标签(保持简单)。
- 模糊层以外的匹配调优(阈值 70% 固定,放审查参数设置可选,本次先固定不暴露设置项也可——实现时若 settings schema 加一项 `keyword.fuzzy_threshold` 则顺带,否则硬编码 70% + log 注明)。
