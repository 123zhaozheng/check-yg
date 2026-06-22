# S5 清洗标准化闭环（P0 核心底线）

## 目标
清洗标准化页完整闭环。**核心底线：清洗流水不删减 + 提示词保真**。前端中文化对齐 `stitch_/cleaning_standardization/code.html`（修正红色违规→单色）。后端改 extractor 聚合层 + 新建 FlowRecord 表持久化全部记录（standard/unparsed/excluded）+ raw_payload + 3 个新接口。

## 硬底线（不可违反）
1. **清洗不删减**：1:1 保留。is_valid=false 噪音行 → `unparsed`（不丢）；classifier 判非流水表的行 → `excluded`（不丢）。每条记录带 `raw_payload`（JSONB，原始全部单元格）。DELETE 走软删。restore 可捞回。
2. **提示词保真**：**禁改** `normalizer.py`/`classifier.py`/`portrait.py` 的 SYSTEM_PROMPT（B1 已 difflib 验证 IDENTICAL）。S5 只改 extractor 聚合层 + 持久化层 + 新增接口。`test_llm_parity.py` 必须仍绿。
3. **单色原则**：禁彩色，禁 `#ba1a1a` 红色。stitch 的 "Anomalies Detected" 红卡 → 改黑底白字粗体（异常数胶囊 bg-ink-900 text-ink-100 font-bold）。行展开原始↔标准对照用浅灰底高亮（bg-ink-200），不用彩色 diff。
4. **Chrome 108 渲染**：禁裸写 color-mix/oklch/lab，用 9 级 ink token。
5. **MinerU 单次 fetch / path-aware identity**：extractor 改造不破坏。
6. **收支修正逻辑忠实**：`_infer_transaction_type`（raw_amount 正负号 + amount_sign_rule）对 standard 记录的修正行为保持与 legacy `flow_extractor_v2.py` 一致，只增强保留，不改正常记录输出。

## 实施决策（2026-06-22 切片定稿）

### 决策1：数据模型 — 新建 FlowRecord 表（推荐方案）
- 新表 `flow_records`：id / task_id / document_id(FK documents) / channel / **record_type**(standard|unparsed|excluded) / row_index / is_valid / transaction_time / counterparty_name / counterparty_account / amount / raw_amount / summary / transaction_type / **raw_payload**(JSONB，原始全部单元格) / status(active|restored) / created_at。
- Alembic migration（revises S4 head `a1c3e5f7b9d2`）。env.py 登记。
- runner `_persist_result_documents` 改为：把 extractor 产出的 standard + unparsed + excluded 全部写入 flow_records（按 document_id 关联预建 Document 行），不再只塞 Document.flow_tables。
- Document.flow_tables 仍可保留汇总（或退役——决策：保留为该文档的表格元信息/统计，flow_records 成为记录真源）。
- records 与 excluded 同表，靠 record_type 过滤。分页/筛选/捞回都是 SQL 原生。

### 决策2：excluded 语义边界
- `excluded` = classifier 判为非流水表（is_flow_table=false 或 confidence<阈值）的**整表原始行**保留。
- `unparsed` = 流水表里 normalizer 标 `is_valid=false` 的噪音行（合计/小计/总计/余额/页脚/页眉/空行）保留。
- 两者都进 flow_records，靠 record_type 区分，都可 restore。
- GET /excluded = record_type in (excluded, unparsed)。

### 决策3：回归验证 — 固定输入 + fake LLM 单测
- 写单测：固定输入（已知表格行 + 画像），monkeypatch fake classifier/normalizer 返固定输出，跑改造后 extractor，断言：
  - standard 记录输出与改造前逻辑等价（字段值逐个比对）。
  - unparsed 行数 = fake normalizer 标 is_valid=false 的行数（不丢）。
  - excluded 行数 = fake classifier 判非流水表的行数（不丢）。
  - 每条 raw_payload 含原始全部单元格。
- 不调真实 LLM（用户已明确推迟真实模型回归）。
- `test_llm_parity.py`（提示词保真）必须仍绿。

### 决策4：规则面板 — 静态列表，命中数不造
- 左面板列固定规则清单（纯展示，不可点不可配）：
  - 日期标准化（YYYY-MM-DD hh:mm:ss）
  - 收支方向推断（raw_amount 正负号 + amount_sign_rule）
  - 金额去符号（amount 正数 / raw_amount 保留正负号）
  - 对手账号纯数字化
  - 噪音行过滤（→ unparsed，不删）
  - 非流水表识别（→ excluded，不删）
- 每项显示描述。命中数显「—」或不显示（后端未统计，不造假数据）。

### 决策5：顶部按钮 — 提交=锁定快照 + 导出日志
- 「提交清洗数据」(黑底主按钮)：将当前 standard 记录锁定为下游可用快照（标记 task 可进入下一阶段 / 或写一个 cleaning_committed 时间戳到 task.config），点击后提示「已提交」+ 跳分析 tab。不重跑清洗。
- 「导出日志」(描边按钮)：导出本次清洗的 unparsed/excluded 日志（CSV 或 JSON，含 raw_payload + 排除原因）。

## 前端范围（`frontend/src/routes/__authenticated/tasks/$id/clean.tsx`）
替换占位为完整清洗标准化页，中文化对齐 stitch（单色改造）：
- **顶部页头**：面包屑 + "清洗与标准化"标题 + 副标题 + 「导出日志」描边按钮 + 「提交清洗数据」黑底主按钮。
- **4 卡统计**：原始记录数 / 标准化记录数 / 排除记录数 / 异常数。
  - 异常数卡 = 黑底白字粗体（bg-ink-900 text-ink-100），**禁红色**。异常数定义 = unparsed + excluded + is_valid=false 计数（或仅 unparsed+excluded，定一个一致口径）。
  - 其他 3 卡白底深灰数字。
- **左规则面板**（w-80）：静态规则列表（决策4），选中项左侧黑竖条。
- **右标准化结果表**：列 记录ID / 日期 / 收支 / 金额(等宽) / 对手 / 渠道 / 摘要 + 筛选排序。
  - 点击行展开原始↔标准对照（双栏，浅灰底高亮 bg-ink-200，禁彩色 diff）。
- **排除项视图**：tab 或切换显示 excluded/unparsed 记录，每条可「捞回」（POST restore）。
- TanStack Query 分页拉 records/excluded。

## 后端范围
- **新表 flow_records**（决策1）+ migration。
- **extractor 改造**：
  - stage1：classifier 判非流水表 → 不 continue 丢弃，把整表原始行产出为 excluded 记录（带 raw_payload）。
  - stage2：normalizer 返回的行 → is_valid=true 入 standard，is_valid=false 入 unparsed（带 raw_payload），都不丢。
  - 收支修正 `_infer_transaction_type` 只对 standard 应用，逻辑忠实 legacy。
  - result 结构扩展：flow_records(standard) + unparsed_records + excluded_records，或统一 records 列表带 type。
- **runner `_persist_result_documents`**：把全部记录写 flow_records（按 document_id 关联）。
- **3 个新接口**（tasks.py）：
  - `GET /api/tasks/{id}/records?channel=&status=&page=&page_size=`：返 standard 记录分页（默认 status=standard，可切 excluded/unparsed/all）。
  - `GET /api/tasks/{id}/excluded?page=`：返 excluded+unparsed 记录（可捞回项）。
  - `POST /api/tasks/{id}/records/{record_id}/restore`：把 excluded/unparsed 记录标 restored（status=restored），可选提升回 standard（若用户确认是流水）——决策：restore = 标记 restored + 在排除项视图隐藏，记录仍在表（不删减）；是否提升回 standard 留给后续切片，本切片 restore = 标记已捞回。
- owner-only 校验复用 `_load_owned_task`。

## api.ts（只追加）
FlowRecordItem / RecordListResponse / listTaskRecords(taskId, params) / listExcluded(taskId, params) / restoreRecord(taskId, recordId) 类型与函数。

## 验收
- chrome108 渲染正常，无红色违规（异常数黑底白字）。
- 记录 1:1（standard + unparsed + excluded = 原始全部行，无丢失）。
- 原始↔标准对照清晰（行展开双栏，浅灰底高亮）。
- 排除项可查看可捞回。
- 回归 diff：固定输入单测，standard 输出等价改造前，unparsed/excluded 不丢，raw_payload 完整。
- `test_llm_parity.py` 提示词保真测试仍绿。
- 后端全量测试绿，前端 build 通过。

## 不做（留给后续切片）
- AI 分析（S6）、报告（S7）、导出（S8）。
- 清洗规则可配置/重洗（固定不可调）。
- 真实模型回归（用户推迟）。
- restore 提升回 standard 的完整流程（本切片仅标记 restored）。
