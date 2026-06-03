# PRD: 已完成任务新增流水目录

## 背景

业务反馈：任务处理完成后，无法在原始任务上新增文档，只能创建新任务。这导致同一个审计对象的相关文档被拆散到多个任务中，不便于管理和查看。

## 核心需求

在已完成（`completed`）任务的三个点菜单（⋮）中，增加"新增流水目录"选项。点击后弹出文件夹选择器，选完直接开始处理新文档，结果追加到已有任务中。

## 详细设计

### 1. 菜单变更（`home_page.py` TaskCard._show_menu）

- 在 `completed` 状态下，"查看详情"和"删除记录"之间增加"新增流水目录"菜单项
- 点击后弹出文件夹选择对话框（复用 `FileSelector` 或 `QFileDialog`）
- 选完后触发追加处理流程

### 2. 数据结构变更（`checkpoint_manager.py`）

- `document_folder` 字段从 `str` 改为 `List[str]`，记录所有添加过的文件夹路径
- 加载旧数据时自动兼容：如果 `document_folder` 是字符串，转为 `[字符串]`
- 新增方法 `append_documents(task_id, new_folder, new_documents)`：
  - 将新文件夹路径追加到 `document_folder` 列表
  - 将新文档路径追加到 `documents` 列表（去重：按文件路径跳过已有文档）
  - 将任务状态更新为 `extracting`
  - 为新文档创建断点文件

### 3. 提取流程变更（`flow_extractor_v2.py`）

- 新增入口方法 `extract_flows_append(task_id, new_folder)`：
  - 扫描新文件夹
  - 过滤掉已有文档（按路径去重）
  - 如无新文档，返回提示
  - 为新文档创建断点
  - 执行提取+规范化流程（复用现有逻辑）
  - 完成后更新任务状态：全部成功 → `completed`，有失败 → `failed`

### 4. UI 交互

- 点击"新增流水目录" → 弹出文件夹选择对话框 → 选完直接开始处理
- 空目录提示：扫描后无文件时，弹出提示"该目录下未找到可处理的文档"，不改变任务状态
- 追加处理期间，任务卡片状态显示为"提取中"（复用现有进度展示）
- 追加处理支持取消（复用现有取消机制）

### 5. 输出处理

- 追加完成后，覆盖 JSON 报告文件（`extract_{task_id}.json`）
- Excel 导出由用户手动触发，自动包含全部数据（旧+新）

### 6. 不变的项

- 任务标题保持不变
- 已有文档结果保留不动
- 不重建旧文档断点
- 失败处理逻辑和初次提取一致

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `src/ui/pages/home_page.py` | 菜单增加"新增流水目录"选项 + 信号 + 弹出文件夹选择 + 触发追加 |
| `src/core/checkpoint_manager.py` | `document_folder` 改列表 + 旧数据兼容 + `append_documents` 方法 |
| `src/core/flow_extractor_v2.py` | 新增 `extract_flows_append` 方法 |
| `src/ui/main_window.py` | 连接追加信号到提取器 |

## 验收标准

1. `completed` 状态的任务，三个点菜单出现"新增流水目录"
2. 点击后弹出文件夹选择，选完直接开始处理
3. 空目录弹出提示，不改变任务状态
4. 追加后状态回退为 `extracting`，跑完后变为 `completed`/`failed`
5. 已有文档结果不受影响
6. `document_folder` 列表包含所有添加过的文件夹
7. 旧任务数据加载正常（字符串自动转列表）
8. 重复文档按路径去重跳过
9. 支持取消追加处理
10. Excel 导出包含全部数据
