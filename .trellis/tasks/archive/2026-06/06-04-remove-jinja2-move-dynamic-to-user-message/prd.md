# PRD: 移除 Jinja2 注入，动态数据统一放 user message

## 背景
当前 3 个 LLM 模块（分类器、标准化器、画像提取器）的系统提示词都使用 Jinja2 `{{ variable }}` 注入动态内容。这导致：
1. 系统提示词本应是固定指令，混入动态数据后每批请求都不同
2. 动态数据（画像、表头、预览等）更适合放在 user message 中，与每批变化的数据一起
3. Jinja2 依赖增加了复杂度，且用户在设置页编辑提示词时需理解 Jinja2 语法

## 改动范围

### 1. data_normalizer.py
- 系统提示词 `SYSTEM_PROMPT_DATA_NORMALIZER`：移除 `{{ document_portrait }}`，改为固定文本（纯指令，无动态变量）
- 精简提示词内容（已在对话中完成）
- `_render_prompt()`：移除 Jinja2，直接读取 config 或使用硬编码默认值
- `normalize_rows()`：user message 改为 JSON payload，包含 `document_portrait`、`header_attributes`、`rows`、`source_file`
- 同时修复 `counterparty_account` 混入开户行名称的问题（在提示词铁规则中强调）

### 2. flow_table_classifier.py
- 系统提示词 `SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER`：移除 `{{ document_portrait }}` 和 `{{ content_preview }}`，改为固定文本
- `_render_prompt()`：移除 Jinja2
- `analyze_table()`：user message 中包含 `document_portrait` 和 `content_preview`（当前 content_preview 已在 user message 中，只需把 portrait 也移过去）

### 3. document_portrait.py
- 系统提示词 `SYSTEM_PROMPT_DOCUMENT_PORTRAIT`：移除 `{{ document_name }}`、`{{ non_table_context }}`、`{{ content_preview }}`，改为固定文本
- `_render_prompt()`：移除 Jinja2
- `extract_portrait()`：user message 中包含 `document_name`、`non_table_context`、`content_preview`

### 4. config.py
- `prompt_classifier`、`prompt_normalizer`、`prompt_portrait` 属性：保留（用户仍可在设置页编辑固定提示词），但不再期望含 Jinja2 变量
- 如果用户保存的提示词包含 `{{ }}`，直接当作字面文本输出（不渲染）

### 5. Jinja2 依赖
- `requirements.txt`：考虑移除 `Jinja2>=3.0.0`（如果无其他模块使用）
- `jinja_highlighter.py`：保留（UI 高亮仍有用，帮助用户识别变量占位风格），但提示词不再依赖

### 6. UI 设置页
- AI 提示词 tab 的 3 个编辑器：仍可编辑，只是不再注入变量
- Jinja2 高亮器：保留，作为视觉辅助

## 不改动的
- `_infer_transaction_type` 代码逻辑不变
- `_infer_document_context` 兜底逻辑不变
- 用户设置页 UI 结构不变
- jinja_highlighter.py 保留（UI 装饰用途）
