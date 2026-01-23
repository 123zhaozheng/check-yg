# Requirements Document

## Introduction

本文档定义了银行流水审计系统重构的需求。该系统用于从多种格式的文档（PDF、Excel、DOCX）中提取银行流水数据，通过AI智能识别表格结构，将流水数据标准化导出到Excel，然后与客户名单进行匹配审查。

本次重构主要解决现有代码中的逻辑错误、缺失方法和不完整的页面导航问题。

## Glossary

- **Flow_Extractor**: 流水提取器，负责协调文档扫描、表格解析、AI分析和流水提取的核心组件
- **Raw_Table**: 原始表格数据结构，包含从文档中提取的未处理表格内容
- **Header_Mapping**: 表头映射，AI分析后得到的列属性映射关系
- **Flow_Record**: 标准化的流水记录，包含交易时间、交易对手、金额等字段
- **Preview_Page**: 流水预览页面，用于展示提取结果并支持导出和审查操作
- **Review_Page**: 审查配置页面，用于配置客户名单和匹配选项
- **Main_Window**: 主窗口，负责页面导航和全局状态管理
- **Flow_Exporter**: 流水导出器，将流水记录导出为标准Excel格式
- **Customer_Matcher**: 客户匹配器，将流水中的交易对手与客户名单进行匹配

## Requirements

### Requirement 1: 修复流水提取器的文档处理逻辑

**User Story:** As a 审计人员, I want 流水提取器能正确处理所有文档, so that 我可以从文档中提取完整的流水数据。

#### Acceptance Criteria

1. WHEN Flow_Extractor 处理一个文档 THEN THE Flow_Extractor SHALL 完整执行表格提取和AI分析流程而不提前返回
2. WHEN Flow_Extractor 获取到有效的解析器 THEN THE Flow_Extractor SHALL 继续执行后续的表格提取逻辑
3. WHEN Flow_Extractor 处理文档失败 THEN THE Flow_Extractor SHALL 记录错误日志并继续处理下一个文档
4. WHEN Flow_Extractor 完成所有文档处理 THEN THE Flow_Extractor SHALL 返回包含所有流水记录的提取结果

### Requirement 2: 为DOCX解析器添加原始表格提取方法

**User Story:** As a 审计人员, I want DOCX文件能被正确解析, so that 我可以从Word文档中提取流水数据。

#### Acceptance Criteria

1. THE DocxParser SHALL 提供 extract_raw_tables 方法用于提取原始表格数据
2. WHEN DocxParser 解析DOCX文件 THEN THE DocxParser SHALL 返回包含所有表格的 RawTable 列表
3. WHEN DOCX文件包含多个表格 THEN THE DocxParser SHALL 为每个表格生成独立的 RawTable 对象
4. WHEN DOCX表格包含合并单元格 THEN THE DocxParser SHALL 正确处理并保持数据完整性
5. WHEN DocxParser 遇到空表格 THEN THE DocxParser SHALL 跳过该表格并继续处理

### Requirement 3: 实现流水预览页面的导出功能

**User Story:** As a 审计人员, I want 将提取的流水数据导出为Excel文件, so that 我可以在外部工具中查看和编辑数据。

#### Acceptance Criteria

1. WHEN 用户点击导出Excel按钮 THEN THE Preview_Page SHALL 调用 Flow_Exporter 导出所有流水记录
2. WHEN 导出成功 THEN THE Preview_Page SHALL 显示成功提示并告知文件保存路径
3. WHEN 导出失败 THEN THE Preview_Page SHALL 显示错误提示并说明失败原因
4. WHEN 没有流水记录可导出 THEN THE Preview_Page SHALL 显示警告提示并阻止导出操作
5. THE Flow_Exporter SHALL 将流水记录导出到 ~/.check-yg/flows/ 目录下

### Requirement 4: 实现流水预览页面的开始审查功能

**User Story:** As a 审计人员, I want 从预览页面直接开始审查流程, so that 我可以快速进入客户匹配环节。

#### Acceptance Criteria

1. WHEN 用户点击开始审查按钮 THEN THE Preview_Page SHALL 先导出流水Excel文件
2. WHEN 流水导出成功 THEN THE Preview_Page SHALL 发出信号通知主窗口切换到审查页面
3. WHEN 切换到审查页面 THEN THE Review_Page SHALL 自动填充已导出的流水Excel路径
4. IF 流水导出失败 THEN THE Preview_Page SHALL 显示错误提示并阻止页面切换

### Requirement 5: 实现主窗口的页面切换功能

**User Story:** As a 用户, I want 通过侧边栏导航在不同页面间切换, so that 我可以访问系统的各个功能模块。

#### Acceptance Criteria

1. WHEN 用户点击侧边栏导航按钮 THEN THE Main_Window SHALL 切换到对应的页面
2. WHEN 页面切换发生 THEN THE Main_Window SHALL 更新导航按钮的选中状态
3. THE Main_Window SHALL 支持在流水提取、预览、审查、结果四个页面间切换
4. WHEN 流水提取完成 THEN THE Main_Window SHALL 自动切换到预览页面并传递提取结果

### Requirement 6: 实现主窗口的设置对话框功能

**User Story:** As a 用户, I want 通过设置按钮打开配置对话框, so that 我可以修改系统配置参数。

#### Acceptance Criteria

1. WHEN 用户点击设置按钮 THEN THE Main_Window SHALL 打开设置对话框
2. THE SettingsDialog SHALL 允许用户配置 MinerU 服务地址和 LLM API 参数
3. WHEN 用户保存设置 THEN THE SettingsDialog SHALL 将配置持久化到配置文件

### Requirement 7: 简化审查流程

**User Story:** As a 审计人员, I want 审查流程直接读取已导出的流水Excel, so that 审查过程更简单高效。

#### Acceptance Criteria

1. WHEN 开始审查 THEN THE Review_Page SHALL 读取流水Excel文件而非重新解析原始文档
2. THE Customer_Matcher SHALL 从流水Excel中读取交易对手名称列进行匹配
3. WHEN 匹配完成 THEN THE System SHALL 生成审查结果并切换到结果页面
4. THE Review_Page SHALL 支持用户手动选择流水Excel文件路径

### Requirement 8: 完善页面间数据传递

**User Story:** As a 用户, I want 页面间的数据能正确传递, so that 我可以在不同页面间无缝切换而不丢失数据。

#### Acceptance Criteria

1. WHEN 流水提取完成 THEN THE Main_Window SHALL 将提取结果传递给 Preview_Page
2. WHEN Preview_Page 接收到提取结果 THEN THE Preview_Page SHALL 更新统计信息和流水表格
3. WHEN 用户从预览页面开始审查 THEN THE Main_Window SHALL 将流水Excel路径传递给 Review_Page
4. WHEN 审查完成 THEN THE Main_Window SHALL 将审查结果传递给 Result_Page
