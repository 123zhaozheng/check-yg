# Research: llm-modules-current (三个 LLM 模块现状)

- **Query**: B1 — classifier / normalizer / portrait 三模块现状，为 pydantic-ai 替换做底
- **Scope**: internal
- **Date**: 2026-06-22

## Findings

### 0. 总览

三模块都在 `backend/app/llm/`，逐字移植自 legacy `src/llm/` 的成熟提示词，统一用 `httpx.AsyncClient` 直连 OpenAI 兼容 `/chat/completions`，统一 `response_format={"type": "json_object"}`、`temperature=0.1`、重试 3 次、JSON decode 失败兜底。`backend/app/llm/__init__.py:4-6` 导出三个类。

唯一调用方：`backend/app/services/extraction/extractor.py:11` `from ...llm import DocumentPortraitExtractor, FlowDataNormalizer, FlowTableClassifier`，在 `FlowExtractor.__init__` (extractor.py:94-111) 用 `runtime_settings.get("llm.*") or settings.LLM_*` 构造三个实例。runtime settings 由 `ExtractionTaskRunner.start` (runner.py:48) 从 DB 加载。

---

### 1. classifier — `backend/app/llm/classifier.py`

**类**：`FlowTableClassifier` (classifier.py:48)

**构造**：`__init__(self, api_url, api_key, model, timeout=60, max_retries=3)` (classifier.py:64-69)。`api_url` 会被 `.rstrip("/")`，请求拼 `f"{api_url}/chat/completions"` (classifier.py:81)。

**LLM 调用**：`_post(system_prompt, user_message)` (classifier.py:71-135) — `httpx.AsyncClient(timeout=self.timeout, trust_env=False)` → POST → `data["choices"][0]["message"]` → 取 `content or reasoning_content or reasoning` → `json.loads`。重试循环 `for attempt in range(self.max_retries)`，`JSONDecodeError` 和其他 Exception 分别 warning 后继续。**`trust_env=False` 关掉代理/env 读取**，B1 换 pydantic-ai 后 `OpenAIProvider` 默认走 `AsyncOpenAI`，要显式 `http_client=httpx.AsyncClient(trust_env=False)` 才等价。

**payload**（classifier.py:86-95）：`model` + 两条 messages + `temperature=0.1` + `max_tokens=1500` + `response_format={"type": "json_object"}`。

**输入**：`classify(table: RawTable, document_name: str, document_portrait: Optional[dict]=None) -> dict` (classifier.py:137-175)。`RawTable` 在 `backend/app/parsers/base.py:66-95`，`get_preview(max_rows=10)` 拼成 `<table>...<tr><td>...</td></tr>...</table>` HTML 字符串。

**user_message 拼装**（classifier.py:159-163）：
```
文档名称：{document_name}

文档画像：{json.dumps(document_portrait, ensure_ascii=False) if document_portrait else '无'}

请分析以下表格：

{preview}
```

**输出契约**：dict，键 `is_flow_table(bool)` / `confidence(0-100 int)` / `reason(str)` / `header_row_index(int, 无表头 -1)` / `data_start_row(int, 无表头一般 0)`。失败返回 `FALLBACK_RESULT` (classifier.py:56-62) `{is_flow_table:False, confidence:0, reason:"classification unavailable", header_row_index:-1, data_start_row:0}`。`classify` 末尾 `result.setdefault(...)` 五个键兜底 (classifier.py:170-174)。空表直接返回 `dict(FALLBACK_RESULT, reason="empty table")` (classifier.py:155-156)。

**完整系统提示词**（classifier.py:20-45，逐字）：

```
你是一个银行/支付流水表格识别专家，熟悉中国各大银行、信用卡、支付宝、微信等流水格式。

## 任务
根据文档画像与表格预览内容，判断是否为流水表格。

## 关键判断要点
- 每行代表一笔交易，通常包含日期/时间、金额、对手方/商户、摘要/备注等
- 即使表格没有明显表头（分页续表），但行结构像流水，也应判断为流水表格
- 只有1-2行数据通常不是流水表格
- 账户信息/汇总统计/账单首页不是流水表格

## 文档画像参考
画像数据在下方用户消息中提供，请参考画像信息进行判断。

## 内容预览
预览数据在下方用户消息中提供，请参考预览内容进行判断。

## 返回JSON格式
{
  "is_flow_table": true或false,
  "confidence": 0-100整数,
  "reason": "判断理由",
  "header_row_index": 表头行索引（无表头则为-1）,
  "data_start_row": 数据开始行索引（无表头一般为0）
}
```

**调用方在 extractor**：`extractor.py:408-410` `classification = await self.classifier.classify(table, doc_path.name, document_portrait=portrait)`，之后 `extractor.py:414-428` 按 `is_flow_table and confidence >= confidence_threshold` 过滤、读 `header_row_index`/`data_start_row` 切 `table.rows[data_start_row:]`。

---

### 2. normalizer — `backend/app/llm/normalizer.py`

**类**：`FlowDataNormalizer` (normalizer.py:97)

**构造**：同 classifier，`__init__(api_url, api_key, model, timeout=60, max_retries=3)` (normalizer.py:105-110)。

**LLM 调用**：`_post` (normalizer.py:112-176) 与 classifier 同构，唯一差别 `max_tokens=4000`（normalizer.py:134，因 rows 多）。

**输入**：`normalize(rows: List[List[str]], document_portrait: Optional[dict]=None, source_file: str="") -> List[dict]` (normalizer.py:178-223)。`rows` 是原始表格行（每行单元格字符串列表）。空 rows 直接返回 `[]` (normalizer.py:197-198)。

**portrait 兜底**：`document_portrait is None` 时调 `_infer_document_context(source_file)` (normalizer.py:200-202, 225-268)，按文件名关键字推 `account_type`：`信用卡/credit/贷记卡` → `credit_card`，`支付宝/alipay` → `alipay`，`微信/wechat/weixin` → `wechat`，否则 `bank_general`。每类带 `document_type` + `document_type_hints` 列表。**这是 portrait 提取失败时的兜底，B1 必须保留**。

**user_message 拼装**（normalizer.py:206-217）：先把 `rows` 转成 `payload_rows = [{"row_index": index, "cells": [str(cell) for cell in row]} ...]`（column_mapping 按位置解析需要 row_index），再 `json.dumps({"document_portrait": portrait, "rows": payload_rows, "source_file": source_file}, ensure_ascii=False)`。

**输出契约**：`List[dict]`，每项 `{row_index, is_valid(bool), transaction_time, counterparty_name, counterparty_account, amount, raw_amount, summary, transaction_type, source_file}`。失败返回 `[]` (normalizer.py:220-221)。从 `result.get("rows", [])` 取（normalizer.py:223）。

**铁规则（提示词内）**：`amount` 始终正数无负号；`raw_amount` 保留原始正负号；`transaction_type` 只允许 `"收入"` / `"支出"`；`counterparty_account` 仅纯数字账号；`is_valid=false` 过滤噪音行（合计/小计/总计/余额/页脚/页眉/空行）。

**完整系统提示词**（normalizer.py:26-94，逐字）：

```
你是一个银行/支付流水数据标准化专家。

## 任务
给定文档画像（含列映射）以及若干行原始表格数据，输出标准化流水记录。

## 标准字段
1) transaction_time - 交易时间（日期或日期时间）
2) counterparty_name - 交易对手/商户名称
3) counterparty_account - 交易对手账号/卡号（仅纯数字/卡号，无则为空）
4) amount - 交易金额（正数，不含负号）
5) raw_amount - 原始金额（保留源文档原始正负号，如"-795.42"、"1200.00"，无符号则为原值）
6) summary - 摘要/备注/交易说明/商品信息
7) transaction_type - 收支类型（只允许"收入"或"支出"）
8) source_file - 来源文件名

## 列映射规则
用户消息中 document_portrait 包含 header_attributes 和 column_mapping 两个有序数组，一一对应。
- 严格按 column_mapping 填充，映射到的列内容原封不动还原（不做改写/缩写/翻译）
- 映射值为 null 的列忽略
- 映射值为数组的列，该列内容填入数组中所有目标字段
- transaction_type：允许语义归纳（如"借"→"支出"，"贷"→"收入"，"收"→"收入"）
- summary：允许从多列拼接或提炼关键词
- 其余字段（transaction_time, counterparty_name, counterparty_account, amount）必须原封不动还原原文档内容
- 若 column_mapping 缺失，尽力根据行内容自行判断映射

## 铁规则
1. amount 始终为正数，禁止出现负号；raw_amount 保留原始正负号
2. transaction_type 只允许"收入"或"支出"
3. counterparty_account 仅填纯数字账号/卡号，禁止填入开户行、银行名称等非数字内容，无账号列为空
4. 过滤噪音行（合计/小计/总计/余额/页脚/页眉/空行），is_valid=false

## 收支方向判断（仅代码无法确定时由你判断）
代码已根据 amount_sign_rule + raw_amount 正负号确定收支方向的场景，你无需再判断。以下场景需你判断：
- amount_sign_rule=no_sign：无正负号，按摘要/收支列语义判断
- amount_sign_rule=split_cols：收入列→"收入"，支出列→"支出"
- amount_sign_rule=unknown：综合判断，正负号优先于摘要
- account_type=credit_card：按交易语义判断（消费→支出，还款/退款→收入）

## 字段清洗
1. 日期统一 "YYYY-MM-DD hh:mm:ss"，仅日期补 "00:00:00"，缺秒补 ":00"
2. 日期缺年推断：若表格日期仅含月日无年份（如"12/15"、"1月3日"），必须结合画像信息推断年份：
   - 优先使用 statement_period 中的年份或日期范围
   - 若 account_type=credit_card 且画像含出账单日/账单周期：注意账单跨年场景（如1月出账单覆盖上年12月消费，则12月日期应为上一年）
   - 参考 key_observations 中的年份提示
   - 无法推断年份时保持原样，禁止猜测
3. 金额去除前缀（"RMB""￥""¥"", ""），amount 去负号，raw_amount 保留原值
4. 若只有一个"交易描述/商户名称"列，counterparty_name 与 summary 可相同

## 文档画像
画像数据在下方用户消息中提供，请参考画像信息进行标准化。

## 返回JSON格式
{
  "rows": [
    {
      "row_index": 原始行号,
      "is_valid": true或false,
      "transaction_time": "...",
      "counterparty_name": "...",
      "counterparty_account": "...",
      "amount": "...",
      "raw_amount": "...",
      "summary": "...",
      "transaction_type": "...",
      "source_file": "..."
    }
  ]
}
```

**调用方在 extractor**：`extractor.py:511-513` `normalized = await self.normalizer.normalize(batch, portrait, source_file=doc_path.name)`。之后 `extractor.py:519-536` **代码侧后处理 transaction_type**：对非信用卡账户，用 `raw_amount` 正负号 + `amount_sign_rule` 推断，若与 LLM 判定不一致则覆盖（`_infer_transaction_type` 静态方法 extractor.py:127-160）。`extractor.py:538-550` 把 valid 项转 `FlowRecord`（**注意：FlowRecord 不含 raw_amount 字段**，见下）。

---

### 3. portrait — `backend/app/llm/portrait.py`

**类**：`DocumentPortraitExtractor` (portrait.py:94)

**构造**：同上 (portrait.py:101-106)。`max_tokens=1500` (portrait.py:130)。

**LLM 调用**：`_post` (portrait.py:108-172) 同构。

**输入**：`extract(document_name: str, non_table_context: str, content_preview: str="") -> Optional[dict]` (portrait.py:174-216)。`non_table_context` 是 PDF/DOCX 抽出的非表格文本，`content_preview` 是表格预览（用于金额符号规则识别）。`is_available()` 检查 `api_key` (portrait.py:218-219)，`extract` 开头 `if not self.api_key: return None` (portrait.py:191-192)。

**user_message 拼装**（portrait.py:200-207）：`json.dumps({"document_name": ..., "non_table_context": ..., "content_preview": ...}, ensure_ascii=False)`，无系统提示词里那种 `无` 兜底。

**输出契约**：`Optional[dict]`，成功时含 `account_type` / `account_holder` / `account_number_masked` / `institution` / `statement_period` / `key_observations(list)` / `amount_sign_rule` / `header_attributes(list)` / `column_mapping(list)`。失败返回 `None`（不是兜底 dict）。`PORTRAIT_FIELDS` 常量列了 9 个键 (portrait.py:81-91)。

`account_type` 枚举：`credit_card / debit_card / alipay / wechat / bank_general / unknown`。
`amount_sign_rule` 枚举：`pos_income / pos_expense / no_sign / split_cols / unknown`。

**完整系统提示词**（portrait.py:18-77，逐字）：

```
你是一个银行/支付文档画像提取专家。

## 任务
根据文档名称、非表格文本内容与表格数据预览，提取文档的结构化画像信息，以及流水表格的表头属性列表及其与标准字段的映射关系。

## 画像字段说明
- account_type: 账户类型，必须为 credit_card/debit_card/alipay/wechat/bank_general/unknown 之一
- account_holder: 户名/持卡人/账户名，无法确定则为空
- account_number_masked: 脱敏账号/卡号，无法确定则为空
- institution: 银行/支付机构名称，无法确定则为空
- statement_period: 账单周期/流水时间范围，无法确定则为空
- key_observations: 关键观察列表，包含文档中的特殊标识、关键特征词等
- amount_sign_rule: 金额符号规则，必须为以下英文标识之一：
  - pos_income: 正数=收入，负数=支出（如"收入/支出金额"列，正数对应存入/转入）
  - pos_expense: 正数=支出，负数=收入（如信用卡账单，正数对应消费/刷卡）
  - no_sign: 金额无正负号，靠摘要/收支列判断
  - split_cols: 收入/支出分两列（或借方/贷方双列）
  - unknown: 无法判断
- header_attributes: 有序数组，按列顺序列出流水表格的表头名
- column_mapping: 有序数组，与 header_attributes 一一对应，值为标准字段名/数组/null

## 判断要点
- 文件名中的"信用卡/贷记卡/Credit"→ account_type=credit_card
- 文件名中的"储蓄卡/借记卡"→ account_type=debit_card
- 文件名中的"支付宝/Alipay"→ account_type=alipay
- 文件名中的"微信/WeChat"→ account_type=wechat
- 非表格文本中的账户信息、账单周期、机构名称等也应提取
- 特别注意提取年份信息：非表格文本中出现的年份（如"2025年"、"2026年"）、账单出账日、结算周期等，这些信息对后续流水日期标准化至关重要，务必记录到 statement_period 或 key_observations 中
- 无法确定的字段留空，不要猜测
- 观察金额列数值是否包含负号：如有负号，判断正数和负数分别对应什么交易类型
- 若金额列全部为正数或绝对值，无负号 → no_sign
- 若存在"收入金额"+"支出金额"或"借方金额"+"贷方金额"两列 → split_cols
- 若正数行对应存入/转入/贷款发放等，负数行对应扣款/转出/还款等 → pos_income
- 若正数行对应消费/刷卡/分期等，负数行对应还款/退款等（信用卡常见） → pos_expense

## 映射指导
8个标准字段：transaction_time, counterparty_name, counterparty_account, amount, raw_amount, summary, transaction_type, source_file
映射规则：
- 原表头名与标准字段语义匹配时映射为对应标准字段名字符串
- 一对多时用数组，如"交易描述"同时映射到 ["counterparty_name","summary"]
- 无法映射时为 null
- split_cols 场景：借方金额/贷方金额两列都映射到 "amount"
- raw_amount 和 source_file 不需要映射（raw_amount 由标准化器从 amount 列推导，source_file 由代码填充）

## 输入
输入数据（文档名称、非表格内容、表格数据预览）在下方用户消息中以JSON格式提供。

## 返回JSON格式
{
  "account_type": "credit_card | debit_card | alipay | wechat | bank_general | unknown",
  "account_holder": "",
  "account_number_masked": "",
  "institution": "",
  "statement_period": "",
  "key_observations": [],
  "amount_sign_rule": "pos_income | pos_expense | no_sign | split_cols | unknown",
  "header_attributes": ["交易日期", "对方户名", "对方账号", "摘要", "借贷", "交易金额", "币种"],
  "column_mapping": ["transaction_time", "counterparty_name", "counterparty_account", "summary", "transaction_type", "amount", null]
}
```

**调用方在 extractor**：`extractor.py:397-399` `portrait = await self.portrait_extractor.extract(doc_path.name, non_table_context, content_preview)`；之后传给 `classifier.classify(..., document_portrait=portrait)` (extractor.py:409) 和 `normalizer.normalize(batch, portrait, ...)` (extractor.py:512)。checkpoint 里也存 `portrait` (extractor.py:474)。

---

### 4. FlowRecord 模型定义（标准化记录）

**定义在** `backend/app/parsers/base.py:28-63`，是 `@dataclass`（不是 SQLAlchemy 模型，**不在 DB 里**）：

```python
@dataclass
class FlowRecord:
    source_file: str = ""
    original_row: int = 0
    transaction_time: str = ""
    counterparty_name: str = ""
    counterparty_account: str = ""
    amount: str = ""
    summary: str = ""
    transaction_type: str = ""
```

**注意**：`FlowRecord` **没有 `raw_amount` 字段**。normalizer LLM 输出里有 `raw_amount`，但 `extractor.py:540-549` 构造 `FlowRecord` 时只取 `amount`，丢弃 `raw_amount`（代码侧 `_infer_transaction_type` 先用完 `raw_amount` 再丢）。

**`raw_amount` 的去向**：
- LLM 输出 → `normalized` list (extractor.py:511)
- `_infer_transaction_type` 读 `item["raw_amount"]` 推 transaction_type (extractor.py:523-525)
- 构造 `FlowRecord` 时**不传入** (extractor.py:540-549) → 丢弃
- 但 checkpoint 里存的是 `record.to_dict()` (extractor.py:560)，所以 checkpoint 也无 `raw_amount`
- `ReviewMatch.record_payload` (review.py:51) 存的是 review_service 从 FlowRecord 拼的 dict，也无 `raw_amount`

**B1 影响**：`docs/research/pydantic-ai-conventions.md` 第 78 行写 `normalizer → output_type=list[FlowRecord]`，但现状 `FlowRecord` 缺 `raw_amount`。两个选择：
1. 给 `FlowRecord` 加 `raw_amount: str = ""` 字段（改 `parsers/base.py`，影响 `to_list`/`to_dict`，波及 export_service 的 Excel 列）；
2. 定义新的 pydantic `BaseModel`（如 `NormalizedRow`）作为 `output_type`，含 `raw_amount` + `is_valid` + `row_index`，agent 返回后再映射成 `FlowRecord`（保留现有 dataclass 不动，影响面最小）。

**推荐方案 2**：pydantic-ai 的 `output_type` 本来就要求 pydantic 模型，`FlowRecord` 是 dataclass 虽然也支持但要加 `@dataclass` 转换；更重要的是 LLM 输出含 `raw_amount`/`is_valid`/`row_index` 三个字段在 `FlowRecord` 里没有，硬塞会丢。新建 `backend/app/llm/types.py` 放 `NormalizedRow(BaseModel)` / `DocumentPortrait(BaseModel)` / `FlowClassification(BaseModel)` 三个 output_type，agent 返回后再在 extractor 里转 `FlowRecord`。这样回归 diff 也好做（直接比 `NormalizedRow` 列表）。

### 5. 现有 LLM 测试 / 回归 fixture

**`backend/tests/test_llm_parity.py`（326 行，最核心）**：

- mock 方式：`_install_fake_post(monkeypatch, responses)` (test_llm_parity.py:49-77) 把 `app.llm.portrait.httpx.AsyncClient` / `app.llm.classifier.httpx.AsyncClient` / `app.llm.normalizer.httpx.AsyncClient` 三处都 patch 成 `_FakeClient`，队列弹 `_FakeResponse` 或 Exception。
- `_FakeResponse` (test_llm_parity.py:25-36) 实现 `raise_for_status` + `json()`，`_chat_response(content)` (test_llm_parity.py:39-46) 构造 `{"choices":[{"message":{"role":"assistant","content":...}}]}`。

**测试用例**：
- portrait：`test_portrait_extracts_expected_field_set` (line 86) 验 9 字段全在；`test_portrait_returns_none_on_malformed_json` (line 121) 验重试到第三次成功；`test_portrait_returns_none_on_empty_content` (line 139)；`test_portrait_returns_none_without_api_key` (line 149)。
- classifier：`test_classifier_returns_header_and_data_row_fields` (line 160) 验 `is_flow_table/header_row_index/data_start_row/reason`；`test_classifier_falls_back_safely_on_failure` (line 183) 验网络异常回 `FALLBACK_RESULT`；`test_classifier_empty_table_returns_fallback` (line 198)。
- normalizer：`test_normalizer_preserves_raw_amount_and_positive_amount` (line 213) — **核心回归断言**：`raw_amount == "-100.00"` 且 `amount == "100.00"` 且 `transaction_type == "支出"`；`test_normalizer_returns_empty_on_failure` (line 250)；`test_normalizer_uses_filename_context_fallback` (line 260) 验 portrait=None 时 `_infer_document_context` 把 `信用卡账单.pdf` 推成 `credit_card`；`test_normalizer_empty_rows_returns_empty` (line 288)。
- 代码侧推断：`test_infer_transaction_type_*` (line 298-325) 五个用例覆盖 `pos_income/pos_expense/credit_card/no_sign/split_cols/empty`。

**其他相关测试**：
- `backend/tests/test_task_extraction_api.py` 有 append 合并、path-aware dedup 的 API 测试，line 165/183/194 验 `flow_records` 合并后 amount 顺序。
- `backend/tests/test_review_fixes.py`、`test_review_export.py` 间接依赖 FlowRecord 结构。

**B1 回归 diff 落点**：`test_llm_parity.py` 的 mock 方式是 patch `httpx.AsyncClient`，换 pydantic-ai 后**整文件要重写**——pydantic-ai 用 `OpenAIProvider(openai_client=AsyncOpenAI(...))`，mock 点变成 `openai.AsyncOpenAI` 或用 `pytest-vcr`/`respx`。但**断言不变**：portrait 9 字段、classifier 5 字段、normalizer 的 `raw_amount`/`amount`/`transaction_type` 三连。这些断言就是"换框架前后输出一致"的验收标准，**逐字保留**。

**建议新增**：`backend/tests/test_llm_parity_diff.py`（或改造现有文件）——固定一组输入 rows + portrait，跑旧 httpx 实现保存 golden output，跑新 pydantic-ai agent，逐字段 diff。task.json 验收 "记录 1:1 + 字段无丢" 对应这个测试。

## Caveats / Not Found

- 三模块的 `max_tokens` 不一致（classifier/portrait 1500，normalizer 4000），换 pydantic-ai 时 `ModelSettings(max_tokens=...)` 要分别设，不能统一。
- 三模块的 `temperature=0.1` 一致，`pydantic-ai-conventions.md` 第 60 行示例写 `temperature=0.0`，**B1 要统一成 0.1 还是 0.0 需要决策**——改 0.0 会影响输出，回归 diff 可能不过。建议保留 0.1 以缩小 diff。
- 三模块都 `trust_env=False`，pydantic-ai 的 `OpenAIProvider` 默认 `AsyncOpenAI` 会读 env 代理，B1 要显式传 `http_client=httpx.AsyncClient(trust_env=False)` 否则内网/ollama 环境可能走代理出问题。
- 没有独立的 fixture 目录（`backend/tests/` 下只有 conftest.py 和 test_*.py，无 `fixtures/`、无 `golden/`、无 `samples/`）。B1 回归 diff 要自备固定输入样本，建议放 `backend/tests/fixtures/llm/` 下（portrait.json + rows.json + expected_normalized.json）。
