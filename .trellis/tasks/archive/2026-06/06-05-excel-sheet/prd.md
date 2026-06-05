# 标准化Excel导出增加星期几/休息日列+汇总Sheet页

## Goal

业务需要在标准化流水Excel导出中：1) 增加星期几和是否休息日两列；2) 增加一个汇总Sheet页，记录每个文档的标准化流水数及成功/失败状态（失败标注原因）。

## Requirements

### 需求1：流水明细Sheet增加两列

- 在现有8列之后追加"星期几"列（格式：周一~周日）和"是否休息日"列（值：是/否/未知）
- 休息日判断使用 `chinesecalendar` 库，按中国法定节假日+调休安排判断
- **【关键约束】星期几和是否休息日必须纯程序化计算**，严格基于 `FlowRecord.transaction_time` 字段用 Python 代码计算，绝不依赖 LLM 推断或猜测。LLM 标准化时不应也不需要生成这两个字段
- 交易时间为空时，星期几和是否休息日均填"未知"
- 交易时间超出 chinesecalendar 覆盖范围时，星期几可从日期推导，是否休息日填"未知"

### 需求2：增加处理汇总Sheet页

- 与流水明细Sheet在同一个Excel中
- 仅包含本次任务处理的文档
- 列结构：文档名称 | 标准化流水数 | 状态（成功/失败） | 失败原因
- 失败原因按阶段描述（如"文档解析失败"、"AI标准化失败"）
- 解析成功但0条流水的文档也显示，状态为"成功"，流水数为0

## Acceptance Criteria

* [ ] 导出的Excel"流水明细"Sheet包含"星期几"和"是否休息日"两列，追加在现有8列之后
* [ ] 星期几显示格式为"周一"~"周日"，交易时间为空时填"未知"
* [ ] 是否休息日与中国法定节假日调休安排一致，交易时间为空或日期超出范围时填"未知"
* [ ] 导出的Excel包含"处理汇总"Sheet页
* [ ] 汇总Sheet正确记录每个文档的标准化流水数
* [ ] 失败的文档标注失败原因（按阶段描述）
* [ ] 解析成功但0条流水的文档在汇总Sheet中显示，状态为"成功"
* [ ] 与 Reviewer 写回逻辑兼容（增加"匹配用户"、"匹配度"列不冲突）
* [ ] 兼容 Python 3.8

## Definition of Done

* 功能实现并通过手动验证
* 不破坏现有导出流程
* 代码风格与现有代码一致
* chinesecalendar 添加到 requirements.txt

## Technical Approach

### 需求1实现

1. 在 `requirements.txt` 中添加 `chinesecalendar` 依赖
2. 在 `src/parsers/base.py` 的 `FLOW_EXCEL_COLUMNS` 常量追加两列
3. 在 `FlowExporter` 的行写入逻辑中（而非 `FlowRecord.to_list()`），基于 `transaction_time` 用 Python 纯程序化计算星期几（`strftime` / `weekday()`）和是否休息日（`chinesecalendar.is_holiday()`），追加到行末
4. 在 `FlowExporter` 中更新 `COLUMN_WIDTHS` 和列头样式
5. 在 `reviewer.py` 的写回逻辑中适配新增列（列偏移）

### 需求2实现

1. 在 `ExtractionResult` 中新增 `per_document_stats: Dict[str, Dict]` 字段，跟踪每个文档的标准化流水数
2. 在 `flow_extractor_v2.py` 的 `process_doc()` 中将统计信息写入 `ExtractionResult.per_document_stats`
3. 在 `FlowExporter.export()` 中新增 `extraction_result` 参数，用于生成汇总Sheet
4. 新增 `_write_summary_sheet()` 方法，创建"处理汇总"Sheet
5. 汇总数据来源：`per_document_stats`（成功文档+流水数）、`failed_documents`（失败文档）、`errors`（失败原因）

### 关键决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 休息日判断 | chinesecalendar 库 | 准确、零依赖、支持 Python 3.8、覆盖 2004-2026 |
| 星期几格式 | 周一~周日 | 简短直观，适合Excel列 |
| 空时间处理 | 填"未知" | 明确标识数据缺失 |
| 0流水文档 | 显示为成功 | 完整呈现处理结果 |
| 汇总Sheet位置 | 同Excel额外Sheet | 与流水明细一体化，方便对照 |

## Out of Scope

* 历史任务汇总（仅本次任务）
* 自定义休息日规则
* 除星期几和是否休息日外的更多时间维度列
* 完整错误堆栈记录

## Technical Notes

* 关键文件：`src/export_flows/flow_export.py`（导出逻辑）、`src/parsers/base.py`（列定义、FlowRecord）、`src/core/flow_extractor_v2.py`（提取逻辑）、`src/core/extraction_result.py`（结果数据结构）
* 已有多Sheet先例：`src/core/reviewer.py` 中 `_write_match_details_sheet()` 创建"匹配详情"Sheet
* Reviewer 写回时会在流水明细Sheet增加列，需确保列偏移兼容
* `chinesecalendar` 库：pip install chinesecalendar，import 名为 `chinese_calendar`，API: `is_workday(date)`, `is_holiday(date)`
* 研究文件：`research/chinese-holiday-calendar.md`
