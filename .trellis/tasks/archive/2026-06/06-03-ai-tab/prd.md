# 设置页新增AI提示词Tab与文档画像注入

## Goal

在设置页新增第三个 Tab「AI 提示词」，将当前硬编码的提示词以 UI 展示并支持编辑（Jinja2 模板语法注入动态变量），修改后实时生效。同时引入「文档画像」概念——OCR 后从非表格文本中提取结构化画像替代原来简陋的文件名关键词推断，提升 AI 对文档类型的判断精度，尤其解决信用卡场景下金额正负与收支类型不一致的问题。

## Requirements

### UI 层

- 设置页新增第 3 个 Tab「AI 提示词」，内嵌子 Tab 展示 3 段提示词：画像提取 / 流水表格识别 / 数据标准化
- 提示词编辑器使用 QPlainTextEdit + monospace 字体
- Jinja2 变量 `{{ xxx }}` 通过 QSyntaxHighlighter 浅蓝底色高亮
- 自动保存 + 脏标记：文本变更 debounce 500ms 写入 config.yaml，子 Tab 标签显示小圆点表示有未保存修改，写入成功后消失
- 每个子 Tab 底部有「恢复默认」次要按钮，点击恢复该段默认提示词，弹出确认框防误触
- 设置对话框尺寸放大为 800x700(min) ~ 1000x900(max)
- AI 高级设置页新增 3 项配置：文档画像行数(portrait_lines,默认100)、non_table_context 最大字符数(portrait_max_chars,默认2000)、画像提取并发度(portrait_parallelism,默认2)

### 画像提取层

- OCR 输出 Markdown 后，机械截取所有非表格文本（`non_table_context`，上限 2000 字符可配置）
- 调 LLM 提取结构化画像，输出 JSON：
  ```json
  {
    "account_type": "credit_card | debit_card | alipay | wechat | bank_general | unknown",
    "account_holder": "张三（可为空）",
    "account_number_masked": "6225****1234（可为空）",
    "institution": "招商银行（可为空）",
    "statement_period": "2024年1月-3月（可为空）",
    "key_observations": ["信用卡账单", "本期应还金额为正"]
  }
  ```
- 画像提取与 Classifier 分类**并行**执行（Stage1 内并发），画像结果主要给 Normalizer 用
- 画像提取失败时**降级到 `_infer_document_context()`**，静默降级用户无感知

### 模板层

- 使用 Jinja2 模板语法，提示词中 `{{ variable }}` 在执行时被替换
- 5 个注入点：
  - 画像提取提示词：`{{ document_name }}`、`{{ non_table_context }}`
  - 流水表格识别提示词：`{{ document_portrait }}`、`{{ content_preview }}`
  - 数据标准化提示词：`{{ document_portrait }}`、`{{ header_attributes }}`

### 提示词内容重写

- 标准化提示词中的字段映射参考使用单行 `>` 分隔列表格式：
  ```
  transaction_time: 交易时间 > 交易日期 > 记账日期 > 入账日期 > 日期
  counterparty_name: 对方户名 > 商户名称 > 交易对方 > 对方名称 > 交易描述
  ```
- 金额与收支一致性铁规则 + 反例警示：
  - transaction_type 只允许"收入"或"支出"
  - 支出时 amount 必须为负，收入时 amount 必须为正
  - 信用卡特殊规则优先级高于正负号
  - ❌ 错误示例 + ✅ 正确示例
  - **原始金额不带正负号时，必须根据 transaction_type 补上符号**

### 配置持久化

- 提示词存储在 `~/.check-yg/config.yaml` 的 `prompts` 节下
- 3 段提示词各有默认值（即当前硬编码内容 + 重写后的改进版本）
- 画像配置存储在 `flow_extraction` 节下

## Acceptance Criteria

- [ ] 设置页第 3 个 Tab 可正常展示 3 段提示词（内嵌子 Tab）
- [ ] 提示词可编辑，自动保存到 config.yaml，脏标记正确显示/消失
- [ ] 提示词中的 Jinja2 变量在编辑器中浅蓝高亮
- [ ] 提示词执行时 `{{ }}` 变量被正确替换为实际值
- [ ] OCR 后自动截取 non_table_context 并保存
- [ ] 画像提取 LLM 调用与 Classifier 分类并行执行
- [ ] 画像提取失败时降级到 `_infer_document_context()` 不影响主流程
- [ ] 画像行数、最大字符数、并发度可在 AI 高级设置中配置
- [ ] 信用卡场景下 amount 正负与 transaction_type 一致
- [ ] 原始金额无符号时自动补上
- [ ] 每段子 Tab 的「恢复默认」按钮可正确恢复默认提示词

## Definition of Done

- 功能可通过设置页 UI 完整操作
- 提示词修改后无需重启应用即生效（下次 AI 调用使用新提示词）
- 配置持久化到 config.yaml
- 视觉风格符合极简主义设计规范（黑白灰主色、细线分隔、清晰层级、克制交互反馈）
- Lint / typecheck green

## Decision (ADR-lite)

**Context**: 需要在多条技术路线上做选择
**Decisions**:
| # | 决策点 | 选择 |
|---|--------|------|
| 1 | 模板语法 | Jinja2 |
| 2 | 保存交互 | 自动保存 + 脏标记 |
| 3 | Tab 布局 | 内嵌子 Tab |
| 4 | 画像与分类并行 | 是，画像结果主要给 Normalizer |
| 5 | 画像失败降级 | 回退到 `_infer_document_context()` |
| 6 | 字段映射格式 | 单行 `>` 分隔列表 |
| 7 | 金额规则格式 | 铁规则 + 反例警示 |
| 8 | 变量注入点 | 3 段共 5 个 |
| 9 | 画像配置项 | portrait_lines(100) + portrait_max_chars(2000) + portrait_parallelism(2) |
| 10 | 变量视觉处理 | QSyntaxHighlighter 浅蓝底色 |
| 11 | 恢复默认 | 每个子 Tab 独立恢复 |
| 12 | 对话框尺寸 | 800x700(min) ~ 1000x900(max) |

**Consequences**: 引入 Jinja2 依赖；画像提取增加 LLM 调用成本但精度提升显著；并行策略减少总延迟

## Out of Scope

- 审计报告/问答提示词（REPORT_SYSTEM_PROMPT, QA_SYSTEM_PROMPT）
- 提示词版本管理/历史回滚
- 多语言提示词
- 画像提取结果在 UI 上的展示（仅内部使用）

## Technical Notes

- 关键文件：
  - `src/ui/main_window.py` (SettingsDialog) — 新增 Tab
  - `src/ui/styles.py` — 新增提示词 Tab QSS 样式
  - `src/config.py` — 新增 prompts 配置节 + 画像配置项
  - `src/llm/flow_table_classifier.py` — 提示词改读 config + Jinja2 渲染
  - `src/llm/data_normalizer.py` — 提示词改读 config + Jinja2 渲染
  - `src/llm/document_portrait.py` (新建) — 画像提取 LLM 调用
  - `src/core/flow_extractor_v2.py` — Stage1 并行化改造
  - `src/parsers/pdf_parser.py` — 提取 non_table_context
- 现有 QSS 样式体系已有 thin border + clear hierarchy 基础
- QPlainTextEdit + QSyntaxHighlighter 用于提示词编辑
- Jinja2 需新增依赖
- Research: `.trellis/tasks/06-03-ai-tab/research/pyqt5-minimal-ui.md`
