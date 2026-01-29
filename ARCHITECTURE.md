# 项目架构与编码习惯（PyQt 简版）

## 项目定位
- 桌面端流水审计工具：批量解析文档 → 识别流水表 → LLM 标准化 → 审查匹配 → 导出结果
- 核心逻辑与 UI 分离，业务流程集中在 `src/core/`

## 技术栈
- Python
- PyQt5（桌面 UI）
- requests（LLM HTTP 调用）
- openpyxl/python-docx（Excel/DOCX 解析）

## 目录结构（关键）
- `main.py`：应用入口
- `src/config.py`：全局配置（读取/保存 `~/.check-yg/config.yaml`）
- `src/core/`：核心业务
  - `flow_extractor_v2.py`：两阶段流水提取主流程
  - `reviewer.py`：审查逻辑（客户名单匹配）
  - `checkpoint_manager.py`：断点续跑（按 task_id 保存 JSON）
  - `progress_manager.py`：进度回调
- `src/llm/`：大模型请求
  - `flow_table_classifier.py`：判定是否流水表
  - `data_normalizer.py`：流水标准化
- `src/parsers/`：文件解析（PDF/DOCX/Excel/HTML）
- `src/ui/`：界面层
  - `pages/`：页面级组件（提取/预览/审查/结果）
  - `widgets/`：复用控件
  - `styles.py`：统一样式
- `src/export_flows/`：导出 Excel

## 核心流程（高层）
1. 扫描输入目录（`DocumentScanner`）
2. 阶段 1：逐文档解析表格 → LLM 判断是否流水表（串行）
3. 阶段 2：对流水行做标准化（可并行）
4. 预览/审查 → 导出结果

## 状态与产物
- 配置：`~/.check-yg/config.yaml`
- 断点：`~/.check-yg/checkpoints/{task_id}/`（task.json + doc_*.json）
- 报告：`data/reports/extract_{task_id}.json`

## 编码习惯（项目内风格总结）
- **模块职责清晰**：UI/核心/解析/LLM 分层，互相通过清晰接口调用。
- **配置集中管理**：所有可调参数放在 `Config`，业务代码只读属性。
- **日志优先**：业务异常通过 `logging` 记录，UI 层用提示框反馈。
- **数据结构明确**：`dataclass` 用于结果/匹配等结构化数据（如 `ReviewResult`）。
- **LLM 调用统一封装**：请求逻辑集中在 `src/llm/`，内置超时与重试。
- **断点续跑设计**：每个文档/阶段写入 JSON 状态，便于恢复。
- **UI 组合式写法**：页面/控件分离，使用布局 + 样式表完成界面。

## 适用的维护/扩展思路
- 新增解析格式：加 parser 并在 `FlowExtractorV2._get_parser_for_file` 注册
- 调整 LLM 行为：修改 `src/llm/` 中系统提示词或参数
- 加强日志与诊断：在 `flow_extractor_v2.py` 增加阶段/批次日志
- 提升稳定性：放宽失败策略（如金额非法跳过、LLM 失败重试/降级）
