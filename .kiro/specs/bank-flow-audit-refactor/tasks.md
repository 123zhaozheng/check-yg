# Implementation Plan: Bank Flow Audit System Refactor

## Overview

本实现计划将银行流水审计系统的重构工作分解为可执行的编码任务。任务按照依赖关系排序，确保每个任务都能在前置任务完成后顺利执行。

## Tasks

- [x] 1. 修复流水提取器的文档处理逻辑
  - [x] 1.1 修复 `_process_document` 方法的提前return问题
    - 修改 `src/core/extractor.py` 中的 `_process_document` 方法
    - 移除第89行错误的 `return records, stats`（在 `if not parser` 判断外）
    - 确保有解析器时继续执行表格提取逻辑
    - _Requirements: 1.1, 1.2_
  
  - [x] 1.2 补全 `_extract_raw_tables` 方法对DOCX的支持
    - 在 `_extract_raw_tables` 方法中添加对 `.docx` 文件的处理分支
    - 调用 `parser.extract_raw_tables(file_path)` 获取原始表格
    - _Requirements: 1.1_
  
  - [ ]* 1.3 编写流水提取器单元测试
    - 测试有效解析器时完整执行流程
    - 测试错误处理后继续处理下一文档
    - 测试提取结果完整性
    - **Property 1, 2, 3**
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. 为DOCX解析器添加原始表格提取方法
  - [x] 2.1 实现 `extract_raw_tables` 方法
    - 在 `src/parsers/docx_parser.py` 中添加 `extract_raw_tables` 方法
    - 遍历文档中的所有表格，转换为 `RawTable` 对象
    - 跳过空表格
    - _Requirements: 2.1, 2.2, 2.3, 2.5_
  
  - [x] 2.2 实现 `_table_to_raw` 辅助方法
    - 将 python-docx 的 Table 对象转换为 RawTable
    - 生成 HTML 格式的表格内容
    - 处理合并单元格情况
    - _Requirements: 2.4_
  
  - [ ]* 2.3 编写DOCX解析器单元测试
    - 测试方法存在性
    - 测试多表格文档解析
    - 测试空表格和合并单元格边缘情况
    - **Property 4**
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Checkpoint - 确保解析器和提取器测试通过
  - 运行所有测试，确保通过
  - 如有问题请询问用户

- [x] 4. 实现预览页面的导出和审查功能
  - [x] 4.1 实现 `set_extraction_result` 方法
    - 在 `src/ui/pages/preview_page.py` 中添加方法
    - 保存提取结果到实例变量
    - 更新统计卡片和流水表格
    - _Requirements: 8.2_
  
  - [x] 4.2 实现 `_export_excel` 方法
    - 调用 `FlowExporter` 导出流水记录
    - 处理空数据情况，显示警告
    - 成功时显示文件路径，失败时显示错误
    - 返回导出文件路径或 None
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [x] 4.3 实现 `_on_start_audit` 方法
    - 先调用 `_export_excel` 导出流水
    - 导出成功后发出 `audit_requested` 信号
    - 导出失败时显示错误并阻止切换
    - _Requirements: 4.1, 4.2, 4.4_
  
  - [x] 4.4 添加 `audit_requested` 信号定义
    - 在类定义中添加 `audit_requested = pyqtSignal(str)` 信号
    - 信号携带导出的流水Excel文件路径
    - _Requirements: 4.2, 4.3_
  
  - [ ]* 4.5 编写预览页面单元测试
    - 测试导出功能
    - 测试审查按钮逻辑
    - 测试空数据处理
    - **Property 5, 6**
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4_

- [x] 5. 实现主窗口的页面切换和设置功能
  - [x] 5.1 实现 `_switch_page` 方法
    - 在 `src/ui/main_window.py` 中添加方法
    - 切换 `page_stack` 到指定索引
    - 更新导航按钮的选中状态
    - _Requirements: 5.1, 5.2, 5.3_
  
  - [x] 5.2 实现 `_show_settings` 方法
    - 创建并显示 `SettingsDialog` 对话框
    - _Requirements: 6.1_
  
  - [x] 5.3 添加 PreviewPage 到页面栈
    - 导入 `PreviewPage` 类
    - 在 `_setup_ui` 中创建 `self.preview_page` 实例
    - 将 PreviewPage 添加到 `page_stack`（索引1）
    - _Requirements: 5.3_
  
  - [x] 5.4 完善信号连接
    - 连接 `extraction_completed` 信号到 `_on_extraction_complete`
    - 连接 `preview_page.audit_requested` 信号到 `_on_audit_requested`
    - 实现 `_on_audit_requested` 方法
    - _Requirements: 5.4, 8.1, 8.3_
  
  - [ ]* 5.5 编写主窗口单元测试
    - 测试页面切换
    - 测试导航状态同步
    - 测试信号连接
    - **Property 7, 8**
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3_

- [x] 6. Checkpoint - 确保UI功能测试通过
  - 运行所有测试，确保通过
  - 如有问题请询问用户

- [x] 7. 简化审查流程
  - [x] 7.1 创建 FlowReviewer 类
    - 在 `src/core/reviewer.py` 中实现（如果不存在则创建）
    - 实现 `review` 方法，接收流水Excel和客户名单Excel路径
    - 实现 `_load_flows_from_excel` 方法读取流水数据
    - 实现 `_match_flows` 方法进行名称匹配
    - _Requirements: 7.1, 7.2, 7.3_
  
  - [x] 7.2 定义 ReviewResult 和 MatchRecord 数据类
    - 在 `src/core/reviewer.py` 中定义数据类
    - ReviewResult 包含审查统计和匹配列表
    - MatchRecord 包含单条匹配详情
    - _Requirements: 7.3_
  
  - [x] 7.3 更新 ReviewPage 使用新的审查流程
    - 修改 `_start_review` 方法调用 `FlowReviewer`
    - 确保从流水Excel读取数据而非原始文档
    - _Requirements: 7.1, 7.4_
  
  - [ ]* 7.4 编写审查流程单元测试
    - 测试从Excel读取流水
    - 测试名称匹配逻辑
    - **Property 9**
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 8. 完善页面间数据传递
  - [x] 8.1 实现 `_on_extraction_complete` 方法
    - 在 `MainWindow` 中完善该方法
    - 调用 `preview_page.set_extraction_result(result)`
    - 切换到预览页面
    - _Requirements: 8.1, 8.2_
  
  - [x] 8.2 实现 `_on_audit_requested` 方法
    - 在 `MainWindow` 中添加该方法
    - 调用 `review_page.set_flow_info()` 设置流水信息
    - 切换到审查页面
    - _Requirements: 8.3_
  
  - [x] 8.3 实现 `_on_review_complete` 方法
    - 在 `MainWindow` 中添加该方法
    - 将审查结果传递给 `result_page`
    - 切换到结果页面
    - _Requirements: 8.4_
  
  - [ ]* 8.4 编写数据传递集成测试
    - 测试从提取到预览的数据传递
    - 测试从预览到审查的数据传递
    - 测试从审查到结果的数据传递
    - **Property 10**
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 9. Final Checkpoint - 确保所有测试通过
  - 运行完整测试套件
  - 验证所有功能正常工作
  - 如有问题请询问用户

## Notes

- 任务标记 `*` 的为可选测试任务，可跳过以加快MVP开发
- 每个任务都引用了具体的需求编号以便追溯
- 属性测试验证了设计文档中定义的正确性属性
- Checkpoint 任务用于阶段性验证，确保增量开发的稳定性
