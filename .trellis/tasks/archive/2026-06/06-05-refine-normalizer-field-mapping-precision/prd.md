# PRD: 画像输出列映射 + 分类器精简 + 标准化提示词重构

## 背景
当前管线中，标准化器同时承担"列映射判断"和"数据清洗"两件事，且每批标准化请求独立判断映射，可能导致不一致。
同时分类器输出了 header_attributes，但画像提取器已经能看到表格预览，完全可以更准确地输出表头和映射关系。

## 架构变更

### 当前管线
```
Stage1（串行）:
  分类器 → is_flow_table + header_attributes + data_start_row
  画像提取(并行) → account_type + amount_sign_rule

Stage2: 标准化器(自行判断映射 + 清洗)
```

### 目标管线
```
Stage1（并行）:
  分类器 → is_flow_table + confidence + reason + data_start_row + header_row_index（不输出header_attributes）
  画像提取 → account_type + amount_sign_rule + header_attributes + column_mapping

Stage2: 标准化器(严格按column_mapping填充 + 仅做清洗)
```

## 决策记录（grill-me 15问结论）

1. 映射由画像输出，不是标准化器自行判断
2. 画像提取 + 分类器完全并行（分类器不输出表头，无依赖）
3. 一个文档一个 column_mapping（流水表结构统一）
4. column_mapping 格式：两个平行有序数组，按索引一一对应
5. 映射值：标准字段名字符串，一对多用数组如 ["counterparty_name","summary"]，不映射为 null
6. 分类器仍保留，只输出 is_flow_table + confidence + reason + header_row_index + data_start_row
7. 标准化提示词严格映射 + 例外：summary 和 transaction_type 允许语义归纳，其余原封不动还原
8. 删除标准化提示词中的"映射参考"部分
9. 删除 doc_header_attributes 变量，从 portrait 取 header_attributes 和 column_mapping
10. split_cols 场景：两列都映射到 "amount"，标准化器取非空值
11. 画像失败：降级到文件名推断，标准化器尽力而为，保留日志
12. column_mapping 元素类型：string | array<string> | null

## 详细改动

### 1. document_portrait.py

#### 提示词
新增表头和映射相关说明：
- 任务描述新增"提取流水表格的表头属性列表及其与标准字段的映射关系"
- 画像字段新增：
  - header_attributes: 有序数组，按列顺序列出流水表格的表头名
  - column_mapping: 有序数组，与 header_attributes 一一对应，值为标准字段名/数组/null
- 判断要点新增映射指导：
  - 8个标准字段：transaction_time, counterparty_name, counterparty_account, amount, raw_amount, summary, transaction_type, source_file
  - 映射规则：原表头名与标准字段语义匹配时映射，一对多时用数组，无法映射时为 null
  - split_cols 场景：借方金额/贷方金额两列都映射到 "amount"
  - 交易描述/商户名称等单列可能同时映射到 counterparty_name 和 summary

#### PORTRAIT_SCHEMA 新增
```python
"header_attributes": {
    "type": "array",
    "items": {"type": "string"}
},
"column_mapping": {
    "type": "array",
    "items": {
        "oneOf": [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}},
            {"type": "null"}
        ]
    }
}
```

#### required 列表新增
"header_attributes" 和 "column_mapping"

#### 返回JSON格式示例
```json
{
  "account_type": "debit_card",
  "account_holder": "",
  "account_number_masked": "",
  "institution": "",
  "statement_period": "",
  "key_observations": [],
  "amount_sign_rule": "pos_income",
  "header_attributes": ["交易日期", "对方户名", "对方账号", "摘要", "借贷", "交易金额", "币种"],
  "column_mapping": ["transaction_time", "counterparty_name", "counterparty_account", "summary", "transaction_type", "amount", null]
}
```

### 2. flow_table_classifier.py

#### 提示词精简
- 移除"表头输出规则"部分（不再输出 header_attributes）
- 移除返回JSON中的 header_attributes 字段
- 保留：is_flow_table, confidence, reason, header_row_index, data_start_row

#### CLASSIFIER_SCHEMA 修改
- 移除 header_attributes 属性
- 移除 required 中的 header_attributes

### 3. data_normalizer.py

#### 提示词重构
删除：
- "标准字段映射参考"部分

新增/修改：
- "列映射规则"部分（替代映射参考）：
  严格按 column_mapping 填充：
  - 映射到的列，内容原封不动还原（不做改写/缩写/翻译）
  - 映射值为 null 的列，忽略
  - 映射值为数组的列，该列内容填入数组中所有字段
  - transaction_type：允许语义归纳（如"借"→"支出"，"贷"→"收入"，"收"→"收入"）
  - summary：允许从多列拼接或提炼关键词
  - 其余字段（transaction_time, counterparty_name, counterparty_account, amount）必须原封不动还原原文档内容

保留：
- 标准字段说明
- 铁规则
- 收支方向判断
- 字段清洗

#### normalize_rows() 参数
- 移除 header_attributes 参数
- header_attributes 和 column_mapping 从 document_portrait 中获取

#### user message payload
```python
payload = {
    "document_portrait": document_portrait,  # 含 header_attributes + column_mapping
    "rows": rows,
    "source_file": source_file
}
```

### 4. flow_extractor_v2.py

#### Stage1 修改
- 分类器不再提取 header_attributes，只提取 is_flow_table + data_start_row
- 删除 doc_header_attributes 变量
- 画像提取结果新增 header_attributes + column_mapping

#### Stage2 修改
- 从 document_portrait 中取 header_attributes 和 column_mapping
- 不再从分类器结果中取 header_attributes
- normalize_rows() 调用：移除 header_attributes 参数
- 降级逻辑：画像失败时仍降级到 _infer_document_context，但无 column_mapping，标准化器尽力而为

### 5. _infer_document_context 降级逻辑
- 降级时返回的画像不含 header_attributes 和 column_mapping
- 标准化器检测到无 column_mapping 时，尽力根据行内容自行映射

## 不改动
- _infer_transaction_type 代码逻辑
- UI 设置页 AI 提示词 tab 结构
- jinja_highlighter.py
- checkpoint 序列化格式（header_attributes 改从 portrait 取，checkpoint 可能需要兼容）
