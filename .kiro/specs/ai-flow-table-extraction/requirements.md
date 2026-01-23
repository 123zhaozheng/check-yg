# Requirements Document

## Introduction

本文档定义了 AI 驱动流水表格提取系统 V2 的需求规格。该系统旨在重构现有的流水表格识别系统，完全依赖 AI 来实现表格识别和数据标准化，解决当前表头映射不统一的问题。

系统分为两个主要阶段：
1. **表格提取与流水判断阶段**：串行处理每个文档，提取表格并由 AI 判断是否为流水表格
2. **流水数据标准化提取阶段**：并行处理多个文档，将原始数据转换为统一的 Excel 格式

## Glossary

- **Flow_Table_Extractor**: 流水表格提取系统的核心协调器，负责管理整个提取流程
- **AI_Table_Classifier**: AI 表格分类器，负责判断表格是否为流水表格并提取表头属性
- **AI_Data_Normalizer**: AI 数据标准化器，负责将原始流水数据转换为统一格式
- **Document_Processor**: 文档处理器，负责解析各种格式的文档并提取原始表格
- **Progress_Manager**: 进度管理器，负责跟踪和报告处理进度
- **Checkpoint_Manager**: 断点续作管理器，负责保存和恢复处理状态
- **Header_Attribute_List**: 流水表格表头属性顺序列表，如 `["交易日期", "交易描述", "金额", ...]`
- **Standardized_Record**: 标准化流水记录，包含统一的字段格式

## Requirements

### Requirement 1: 文档表格提取

**User Story:** As a 审计人员, I want to 从各种格式的文档中提取所有表格, so that 我可以进一步分析哪些是流水表格。

#### Acceptance Criteria

1. WHEN 用户提供一个文档文件（PDF、Excel、DOCX）THEN THE Document_Processor SHALL 解析文档并提取所有表格数据
2. WHEN 文档包含多个表格 THEN THE Document_Processor SHALL 按顺序返回所有表格，保留表格在文档中的位置信息
3. WHEN 文档解析失败 THEN THE Document_Processor SHALL 返回错误信息并继续处理其他文档
4. THE Document_Processor SHALL 支持 PDF、Excel（.xlsx/.xls）、DOCX 三种文档格式

### Requirement 2: AI 流水表格判断

**User Story:** As a 审计人员, I want to 让 AI 自动判断每个表格是否是流水表格, so that 我不需要手动筛选表格。

#### Acceptance Criteria

1. WHEN AI_Table_Classifier 接收到一个表格 THEN THE AI_Table_Classifier SHALL 判断该表格是否为流水表格并返回判断结果
2. WHEN AI 判断表格是流水表格 THEN THE AI_Table_Classifier SHALL 在 JSON 输出中返回该表格的 Header_Attribute_List
3. WHEN 表格没有明显表头但格式符合流水特征（可能是分页导致）THEN THE AI_Table_Classifier SHALL 仍然判断为流水表格
4. WHEN AI 判断表格不是流水表格 THEN THE Flow_Table_Extractor SHALL 丢弃该表格
5. FOR ALL 同一文档中的流水表格，THE Flow_Table_Extractor SHALL 使用第一个被判断为流水的表格的表头作为该文档的统一流水表头

### Requirement 3: 流水数据标准化提取

**User Story:** As a 审计人员, I want to 将各种格式的流水数据转换为统一的 Excel 格式, so that 我可以方便地进行后续分析。

#### Acceptance Criteria

1. WHEN AI_Data_Normalizer 接收流水表格数据和对应的 Header_Attribute_List THEN THE AI_Data_Normalizer SHALL 将数据转换为标准化格式
2. THE AI_Data_Normalizer SHALL 输出以下标准字段：transaction_time（交易时间）、counterparty_name（交易对方名称）、counterparty_account（交易对方账号）、amount（交易金额）、summary（摘要/备注）、transaction_type（收支类型）、source_file（来源文件）
3. WHEN 原始数据中的字段名称与标准字段不同（如各银行、微信、支付宝格式差异）THEN THE AI_Data_Normalizer SHALL 根据语义映射到正确的标准字段
4. WHEN 原始数据缺少某个标准字段 THEN THE AI_Data_Normalizer SHALL 将该字段设为空值
5. FOR ALL 标准化后的记录，THE AI_Data_Normalizer SHALL 保留来源文件信息

### Requirement 4: 批量处理与并行化

**User Story:** As a 审计人员, I want to 同时处理多个文档, so that 我可以更快地完成大量文档的流水提取。

#### Acceptance Criteria

1. WHEN 用户上传多个文档（最多 15 个）THEN THE Flow_Table_Extractor SHALL 支持并行处理多个文档的流水提取
2. THE Flow_Table_Extractor SHALL 提供配置选项，允许用户设置一次性发送给 AI 的行数
3. WHEN 处理大量数据时 THEN THE Flow_Table_Extractor SHALL 控制内存占用在合理范围内（15 个文档不超过 500MB）
4. WHILE 并行处理多个文档 THEN THE Flow_Table_Extractor SHALL 确保每个文档的处理结果相互独立

### Requirement 5: 进度状态管理

**User Story:** As a 审计人员, I want to 实时了解处理进度, so that 我可以估计完成时间并监控处理状态。

#### Acceptance Criteria

1. WHILE 处理文档 THEN THE Progress_Manager SHALL 报告当前处理的文档名称、已处理文档数、总文档数
2. WHILE 处理单个文档 THEN THE Progress_Manager SHALL 报告当前处理的表格索引、已处理行数、总行数
3. WHEN 处理状态发生变化 THEN THE Progress_Manager SHALL 通过回调函数通知调用方
4. THE Progress_Manager SHALL 支持以下状态：等待中、处理中、已完成、失败、已取消

### Requirement 6: 断点续作

**User Story:** As a 审计人员, I want to 在处理中断后能够从断点继续, so that 我不需要重新处理已完成的文档。

#### Acceptance Criteria

1. WHILE 处理文档 THEN THE Checkpoint_Manager SHALL 定期将处理状态保存到指定目录
2. WHEN 处理被中断（程序崩溃、用户取消等）THEN THE Checkpoint_Manager SHALL 保留已完成的处理结果
3. WHEN 用户重新启动处理 THEN THE Checkpoint_Manager SHALL 检测已有的断点文件并提供恢复选项
4. WHEN 用户选择从断点恢复 THEN THE Flow_Table_Extractor SHALL 跳过已处理的文档，继续处理未完成的文档
5. WHEN 所有文档处理完成 THEN THE Checkpoint_Manager SHALL 清理断点文件

### Requirement 7: 错误处理与容错

**User Story:** As a 审计人员, I want to 系统能够优雅地处理各种错误, so that 单个文档的失败不会影响整体处理。

#### Acceptance Criteria

1. IF AI 服务调用失败 THEN THE Flow_Table_Extractor SHALL 记录错误并重试（最多 3 次）
2. IF 单个文档处理失败 THEN THE Flow_Table_Extractor SHALL 记录错误并继续处理其他文档
3. IF 单个表格处理失败 THEN THE Flow_Table_Extractor SHALL 记录错误并继续处理同一文档的其他表格
4. WHEN 处理完成 THEN THE Flow_Table_Extractor SHALL 生成处理报告，包含成功/失败的文档列表和错误详情

### Requirement 8: 配置管理

**User Story:** As a 开发人员, I want to 通过配置文件管理系统参数, so that 我可以灵活调整系统行为。

#### Acceptance Criteria

1. THE Flow_Table_Extractor SHALL 从配置文件读取以下参数：AI 服务 URL、模型名称、API Key、批处理行数、并行度
2. WHEN 配置参数缺失 THEN THE Flow_Table_Extractor SHALL 使用合理的默认值
3. THE Flow_Table_Extractor SHALL 支持运行时修改批处理行数和并行度参数

### Requirement 9: Python 3.8 兼容性

**User Story:** As a 开发人员, I want to 系统兼容 Python 3.8, so that 我可以在现有环境中部署。

#### Acceptance Criteria

1. THE Flow_Table_Extractor SHALL 使用 Python 3.8 兼容的语法和标准库
2. THE Flow_Table_Extractor SHALL 不使用 Python 3.9+ 的新特性（如 `|` 类型联合、`match` 语句等）
3. FOR ALL 第三方依赖，THE Flow_Table_Extractor SHALL 选择支持 Python 3.8 的版本
