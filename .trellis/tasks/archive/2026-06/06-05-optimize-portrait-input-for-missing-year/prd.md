# 优化画像生成输入：非表格内容+表格预览，解决信用卡流水缺年问题

## Goal

优化文档画像生成时的输入内容，将非表格内容配额从2000字提升到5000字（可配置），表格预览从100行改为4行（不可配置，全部表格而非仅前3个），画像触发条件改为"有表格就触发"（不再要求必须有非表格内容）；同时在标准化流水提示词中增加"缺年推断"指导，解决信用卡流水等场景中表格日期只有月日无年份的问题。

## Requirements

### 需求1：优化画像输入内容

- 非表格内容配额从2000字提升到5000字（通过config `portrait_max_chars` 配置，默认5000）
- 表格预览从100行改为4行（硬编码为常量 `PORTRAIT_PREVIEW_ROWS = 4`，不可配置）
- 表格预览覆盖所有识别出的表格（不再仅前3个 `raw_tables[:3]`）
- 画像触发条件：只要有表格预览就触发，不再要求必须有 `non_table_context`

### 需求2：标准化提示词增加缺年推断指导

- 在 `SYSTEM_PROMPT_DATA_NORMALIZER` 的"字段清洗"部分增加日期缺年推断规则
- 规则：当表格日期只有月日无年份时，结合画像中的 `statement_period`、`key_observations` 等推断年份
- 特别针对信用卡场景：`account_type=credit_card` + 有出账单日/账单周期信息时，需注意账单周期跨年（如1月出账单覆盖上年12月消费）

## Acceptance Criteria

* [ ] `portrait_max_chars` 默认值从2000改为5000，可通过config配置
* [ ] 画像生成时表格预览固定4行/表，不可配置
* [ ] 画像生成时所有表格都包含在预览中（不限制数量）
* [ ] 画像提取只要有表格预览就触发，不要求必须有非表格内容
* [ ] 标准化提示词"字段清洗"部分包含缺年推断指导规则
* [ ] 规则明确覆盖信用卡账单跨年场景
* [ ] Excel/DOCX 文档现在也能生成画像

## Definition of Done

* 功能实现并通过信用卡流水场景验证
* 不破坏现有画像生成流程
* 代码风格与现有代码一致

## Technical Approach

### 需求1实现

1. `src/config.py`：`portrait_max_chars` 默认值 2000→5000
2. `src/core/flow_extractor_v2.py`：
   - 表格预览构建：`raw_tables[:3]` → `raw_tables`（去掉前3限制）
   - 行数限制：`self.config.flow_portrait_lines` → 硬编码 `4`
   - 画像触发条件：`if non_table_context and self.portrait_extractor.is_available()` → `if raw_tables and self.portrait_extractor.is_available()`
3. 可考虑删除 `portrait_lines` 配置项（不再需要），或保留但不再用于画像预览

### 需求2实现

1. `src/llm/data_normalizer.py`：在 `SYSTEM_PROMPT_DATA_NORMALIZER` 的"字段清洗"部分增加缺年推断规则段落

### 画像提示词优化

1. `src/llm/document_portrait.py`：在画像系统提示词中强调非表格内容可能包含年份、出账单日等关键信息，提醒模型在 `key_observations` 和 `statement_period` 中提取

## Decision (ADR-lite)

**Context**: 信用卡流水表格日期常见只有月日无年份，标准化时模型会错误推断为当年月份
**Decision**: 通过扩大画像输入（更多非表格内容+更多表格预览）让画像模型获取年份信息，再在标准化提示词中显式指导缺年推断
**Consequences**: token消耗可能增加（更多表格预览），但4行预览比100行大幅减少；Excel/DOCX现在也能生成画像

## Out of Scope

* 代码层面自动推断缺年（纯程序化补年，不依赖LLM）
* 修改 `extract_non_table_context()` 为 Excel/DOCX 添加非表格内容提取
* 修改画像输出 schema（新增字段）

## Technical Notes

* 关键文件：`src/llm/document_portrait.py`（画像提示词）、`src/llm/data_normalizer.py`（标准化提示词）、`src/core/flow_extractor_v2.py`（画像调用/预览构建）、`src/config.py`（配置默认值）
* 当前画像触发条件：`flow_extractor_v2.py` 第368行 `if non_table_context and self.portrait_extractor.is_available()`
* 当前表格预览构建：`flow_extractor_v2.py` 第357-363行
* `portrait_lines` 配置项：config.py 第235-237行，默认100
* 画像提示词已提及"非表格文本中的账户信息、账单周期、机构名称等也应提取"（第41行），但未强调年份信息
