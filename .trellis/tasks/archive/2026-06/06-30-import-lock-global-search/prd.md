# 导入流程锁定 + 全局任务搜索跳转

## 背景

数据导入是平台最关键的环节。当前 `import.tsx` 存在三个问题：

1. **处理中可随意追加文件**：`openPicker` → `upload.mutate` 完全不检查 `task.status`，处理中也能加文件。现有注释甚至鼓励「靠 runner 批循环自动接管」。这给用户造成「边加边跑」的混乱心智模型，需要改成**处理中锁定**。
2. **「开始处理」按钮不复位**：`isRunning` 取自 `task.status`，但 `useTask` 无轮询，runner 跑完把 status 置为 `completed` 后前端缓存仍是 `running`，按钮卡在「处理中」。
3. **右上角全局搜索框是死控件**：`app-shell.tsx` L248-255 的 `<input>` 无 onChange、无状态、无行为。

后端调研结论（关键）：
- `runner.py` 的批循环 `_collect_pending_documents` **天然只收集 `pending` 文档**，已 `completed` 的不会重复处理；批循环 `while True` 循环到无 pending 为止。**「再加文件只处理未解析」后端已天然支持，零改动。**
- `list_tasks` 的 `search` 参数只 ilike `title`；`employee_id` 是精确匹配。全局搜索一个框要能同时搜任务名/员工，需要扩展 `search`。

## 目标

- 处理中禁止添加文件（前端拦截 + Dialog 提示）。
- 处理完成后「开始处理」按钮自动复位为可点击状态（轮询 task 详情）。
- 全局搜索框接入：输入 → 下拉候选（任务名/员工匹配）→ 选中跳转 `/tasks/:id`。

## 非目标

- 不改后端 runner / 批循环逻辑（已天然满足）。
- 不改 `append-upload` 端点语义（前端拦截即可，后端仍允许 running 追加作为兜底）。
- 不引入 toast 库（用现有 Dialog 组件）。
- 不改任务列表页 `/tasks` 自身的搜索框（那是页内筛选，与全局搜索独立）。

## 方案

### 1. 导入页处理中锁定（前端拦截）

文件：`frontend/src/routes/__authenticated/tasks/$id/import.tsx`

- 新增一个 `isLocked = taskStatus === "running"` 派生值（沿用现有 `isRunning`）。
- `openPicker`（L162）、`onDrop`（L173）、`onInputChange`（L166）、以及 dropzone 的 `onClick`/`onKeyDown`（L266-274）和「选择文件」按钮（L292）——**全部在最前面加 `if (isLocked) { setShowLockDialog(true); return }` 拦截**。
- 新增一个 `<Dialog>` 状态 `showLockDialog`，内容：「处理进行中，请等待当前批次处理完成后再添加文件。」+ 关闭按钮。
- 现有 `isRunning` 时按钮显示「处理中」（L246-250）保持不变；锁定期间 dropzone 视觉上也可加 `pointer-events-none opacity-60` 弱化（可选，不 blocker）。

### 2. 任务详情轮询（按钮自动复位）

文件：`frontend/src/hooks/use-tasks.ts`

- `useTask(taskId)`（L33-39）增加 `refetchInterval`：当缓存 `data?.status === "running"` 时返回 `2000`（2s），否则返回 `false`（停）。
- 这样 runner 跑完 status 翻 `completed` 后，前端 2s 内感知到，`isRunning` 变 false，按钮回到「开始处理」；同时 `hasPending` 重新评估。
- `useStartExtraction` 的 `onSuccess` 已 invalidate `TASKS_QUERY_KEY`（含 detail），点开始后立即拿到 `running`，轮询随即启动——链路自洽。

### 3. 全局搜索框接入

文件：`frontend/src/components/layout/app-shell.tsx`（L248-255 的静态 input）

- 将静态 `<input>` 改为受控组件：`query` state + debounce 300ms（复用 `tasks/index.tsx` L51-58 的 debounce 模式）。
- debounce 后的值非空时，调 `useTaskList({ search, page_size: 8, archived: false })`（不传 status_filter，全状态搜）。
- 下拉候选面板（绝对定位，input 下方）：每条显示「任务名 · 员工名/工号 · 阶段胶囊」，最多 8 条；点击 → `navigate({ to: '/tasks/$id', params: { id } })` 并清空 query。
- 加载中显示「搜索中…」，无结果显示「无匹配任务」，空 query 时不显示面板。
- 失焦/ESC 关闭面板；点击外部关闭（用一个 `onBlur` 延迟或 `useRef` + mousedown 监听，二选一，实现时定）。

### 4. 后端 search 扩展（任务名 OR 员工）

文件：`backend/app/routers/tasks.py`（L262-263）

- 当前：`query = query.where(Task.title.ilike(f"%{search}%"))`
- 改为：`title OR employee_id OR employee_name` 三者 ilike OR：
  ```python
  query = query.where(
      or_(
          Task.title.ilike(f"%{search}%"),
          Task.employee_id.ilike(f"%{search}%"),
          Task.employee_name.ilike(f"%{search}%"),
      )
  )
  ```
- `employee_id` / `employee_name` 字段均为 `Optional[str]`，`ilike` 对 NULL 安全（NULL 不匹配，符合预期）。
- `employee_id` 精确查询参数（L260-261）保持不变，任务列表页页内筛选继续用精确匹配。
- 需要导入 `from sqlalchemy import or_`（确认 tasks.py 现有 import 行）。

## 验收标准

1. 任务 running 时，在导入页点「上传文件」/「选择文件」/拖拽文件到 dropzone → 弹 Dialog 提示，文件选择器不打开，不上传。
2. 任务 running 期间，`useTask` 每 2s 轮询；runner 完成后 status 翻 `completed`，2s 内「开始处理」按钮自动从「处理中」复位为可点击。
3. completed 任务再加文件 → 文档以 `pending` 入库 → 「开始处理」按钮因 `hasPending` 重新可点 → 点击后 runner 只处理这批新 pending（已 completed 的不重复）。**此条主要靠后端现有能力，前端只验证按钮状态流转正确。**
4. topbar 搜索框输入关键词 → 300ms 后出下拉，匹配任务名/员工名/工号 → 点条目跳到 `/tasks/:id`。
5. 后端 `GET /tasks?search=张` 同时命中 title 含「张」或 employee_name/employee_id 含「张」的任务。
6. 现有测试 `test_report_*` 等不受影响；新增后端测试覆盖 search OR 逻辑。

## 风险 / 注意

- **轮询频率**：2s 一次 task 详情请求，单用户单任务无压力；多 tab 打开同一任务会重复请求，可接受。
- **search OR 性能**：`employee_id`/`employee_name` 无索引时三字段 ilike 全表扫描；当前数据量小，可接受。若后续任务量大需加索引，本任务不做。
- **全局搜索与页内搜索并存**：topbar 搜索是「跳转」语义（选中即跳），`/tasks` 页内搜索是「筛选」语义（留在列表）。两者独立，不冲突。
