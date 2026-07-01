# 流水号可点击弹窗（原始↔标准化对照）

> 现状痛点：关键词审查页「流水行」列、AI 分析页「关联记录」chip 都只显示一个孤零零的
> `#521`，用户认不出这是哪条流水。点了也没反应——既不知道是谁，也不能下钻看详情。
>
> 此次改动：流水号变可点击 → 弹出 Dialog，左侧原始单元格、右侧标准化字段（复用清洗页
> `RawVsStandardCompare` 的双栏对照），让用户一眼看清「这条流水是谁、从哪来、洗成了啥」。

## 决策汇总（grill 已敲定）

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 核心目标 | **纯弹窗可下钻**——不在流水号旁塞摘要，只让 `#id` 可点开看对照 |
| 2 | 接入范围 | **2 处**：关键词审查页「流水行」列 + AI 分析页「关联记录」chip。清洗页余额校验**不动** |
| 3 | 数据获取 | **新增 `GET /tasks/{id}/records/{record_id}` 单条端点**（带 task_id 归属校验） |
| 4 | 弹窗宽度 | **`max-w-3xl`**，双栏各自 `max-h-[60vh] overflow-y-auto` 独立滚 |
| 5 | 弹窗操作 | **纯查看**——无采纳/忽略按钮，操作留在原行/原面板 |
| 6 | 可点击视觉 | **保留各自现有视觉**（关键词审查=纯文字、AI 分析=灰 chip），仅加 hover 反馈 + cursor-pointer |
| 7 | 组件复用 | **抽 `RawVsStandardCompare` 到共享组件**，清洗页原处 + 弹窗都引用 |
| 8 | `finding.id` | **不动**——它是维度发现号非流水号，hover 反馈天然区分，不加 tooltip |

## 现状（代码事实）

- 流水号渲染位置（本次范围内）：
  - `frontend/src/routes/__authenticated/tasks/$id/keyword-review.tsx:307` —— 「流水行」列
    纯文本 `#{hit.flow_record_id}`。
  - `frontend/src/routes/__authenticated/tasks/$id/analyze.tsx:434-441` —— 「关联记录（命中
    流水行）」一排灰 chip `#{rid}`（`rid ∈ finding.evidence_record_ids`）。
- 参考实现：`frontend/src/routes/__authenticated/tasks/$id/clean.tsx:673` `RawVsStandardCompare`
  —— 双栏原始↔标准对照，左 `raw_payload.cells`、右 8 个标准化字段。目前仅清洗页点表格行
  展开时用，未共享。
- 数据层：`FlowRecordItem`（`frontend/src/lib/api.ts:470`）字段齐全含 `raw_payload.cells`；
  但**无单条 GET 端点**——后端 `backend/app/routers/tasks.py:903` 只有分页列表 +
  `POST .../restore`。
- UI 组件：`frontend/src/components/ui/dialog.tsx` 已有 `Dialog` / `DialogHeader` /
  `DialogTitle` / `DialogClose` / `DialogBody`，单色 max-w-lg，支持 ESC 关、点 scrim 关。
- 范围外已确认：清洗页 `clean.tsx:463`（余额校验区）+ `clean.tsx:623`（表格主体行）均不动；
  AI 分析页 `analyze.tsx:345,387` 的 `#{finding.id}`（维度发现号）不动。

## 一、后端：新增单条 GET 端点

- 路由：`GET /api/tasks/{task_id}/records/{record_id}`，放在
  `backend/app/routers/tasks.py` 现有 `list_task_records`（line 903）之后。
- 归属校验：复用 `_load_owned_task(db, task_id, current_user)`（跟现有 records 路由一致），
  确保只能查自己任务的记录，不会越权。
- 查询：`select(FlowRecordRow).where(task_id=?, id=?)`，单条；找不到 → `404`（复用现有
  错误处理风格）。
- 序列化：复用现有 `_record_response(row)`（`tasks.py:880` 附近），响应模型 `RecordResponse`
  （`backend/app/schemas/review.py`，与列表项同模型）。
- 不加新字段、不动模型、不动列表端点。

## 二、前端：共享组件 + Dialog + Link

### 2.1 抽取共享对比组件

- 新文件 `frontend/src/components/flow-record-compare.tsx`，把 `RawVsStandardCompare` 从
  `clean.tsx:673` **原样搬出**（双栏 flex 内容渲染，接收 `{ row: FlowRecordItem }`）。
- `clean.tsx` 改为 `import { RawVsStandardCompare } from "@/components/flow-record-compare"`，
  删本地定义——**零行为变化**（清洗页就地展开布局不变）。
- 组件只负责双栏内容；滚动容器由调用方包（清洗页不包，弹窗内包 `max-h-[60vh]`）。

### 2.2 单条记录 hook + API

- `frontend/src/lib/api.ts`：新增 `getTaskRecord(taskId, recordId): Promise<FlowRecordItem>`，
  GET `/tasks/{taskId}/records/{recordId}`。
- `frontend/src/hooks/use-records.ts`：新增 `useFlowRecord(taskId, recordId)`，TanStack Query
  标准用法（queryKey 含 recordId，`enabled: recordId != null`），缓存交给默认 staleTime——
  同一条重复点不重发。

### 2.3 FlowRecordLink（可点击流水号 + 受控弹窗，二合一）

- 新文件 `frontend/src/components/flow-record-link.tsx`，导出 `<FlowRecordLink>`：
  - props：`{ taskId: number; recordId: number; variant?: "plain" | "chip" }`。
  - 内部维护 `open` state，渲染触发器 + `<Dialog>`。
  - 触发器渲染 `#{recordId}`：
    - `variant="plain"`（默认，关键词审查用）：纯文字 + `cursor-pointer` + hover 加深 bg +
      下划线。
    - `variant="chip"`（AI 分析用）：保留现有 chip 视觉（`border bg-ink-200 px-2 py-0.5`）+
      hover bg 加深 + cursor。
  - 点击 → `setOpen(true)` → Dialog 打开，hook 拉单条数据。
  - 单色硬底线：hover 反馈只用灰阶（bg-ink-300），禁彩色。

### 2.4 Dialog 内容

- 用现有 `<Dialog>`（`max-w-3xl` 覆盖默认 max-w-lg）+ `DialogHeader`（标题「流水详情
  `#{recordId}`」+ `DialogClose`）+ `DialogBody`。
- Body：外层 `<div className="flex gap-6">`，左右各 `<div className="max-h-[60vh]
  overflow-y-auto">` 包住 `<RawVsStandardCompare row={record} />` 的两栏（即组件渲染双栏，
  调用方在每栏外包滚动容器——或组件接受 `scrollable` prop，二选一，实现时定）。
- loading：`<div>加载中…</div>`（与全站空态文案一致）。
- error（404 / 无权限）：`<div>该流水记录不存在或已删除</div>`（不暴露 403/404 细节）。
- 无 footer 操作按钮（纯查看）。

### 2.5 两处接入

- `keyword-review.tsx:305-309`：把 `<span>#{hit.flow_record_id}</span>` 换成
  `<FlowRecordLink taskId={taskId} recordId={hit.flow_record_id} variant="plain" />`。
- `analyze.tsx:432-448`：把 `evidenceIds.map((rid) => <span chip>#{rid}</span>)` 换成
  `evidenceIds.map((rid) => <FlowRecordLink taskId={taskId} recordId={rid} variant="chip" />)`。

## 三、硬约束

- **单色硬底线**：弹窗、Link、hover 反馈全部灰阶（bg-ink-* ），禁任何彩色（红/黄/绿/蓝），
  跟全站一致。
- **不动清洗页行为**：`RawVsStandardCompare` 抽出后清洗页就地展开必须**视觉与交互完全不变**
  （只改 import 来源，不动布局）。
- **纯查看**：弹窗内不放任何采纳/忽略/备注按钮，操作留在原页面。
- **归属校验**：后端单条端点必须 `_load_owned_task`，防越权查别人任务的记录。
- **不塞摘要**：流水号旁不加日期/金额/对手等识别信息（决策 1 明确——纯弹窗下钻）。
- **不动 finding.id**：AI 分析页维度发现号不加 tooltip、不改交互。

## 四、非目标（不做）

- ❌ 流水号旁塞摘要信息（日期/金额/对手）——决策 1 已排除。
- ❌ 清洗页接入（余额校验 + 表格主体行均不动）——决策 2 已排除。
- ❌ `finding.id` 加 tooltip / 改交互——决策 8 已排除。
- ❌ 弹窗内放操作按钮（采纳/忽略/备注）——决策 5 已排除。
- ❌ 流水号统一成单一视觉样式——决策 6 已排除（保留各自上下文样式）。
- ❌ 批量流水号联动（点一个看一个，不做多选/翻页）。
- ❌ 后端加 id 过滤参数到列表端点（不做决策 3 的 option c 折中）。

## 验收（DoD）

- [ ] 后端新增 `GET /tasks/{id}/records/{record_id}`，返回 `RecordResponse`；找不到 404；
  非本人任务 403/404（跟 `_load_owned_task` 现有行为一致）。
- [ ] 后端单测：存在 / 不存在 / 越权 三 case（参考现有 records 测试风格）。
- [ ] `RawVsStandardCompare` 抽到 `components/flow-record-compare.tsx`，`clean.tsx` 改 import
  后清洗页就地展开**视觉零变化**（手测点行展开对照）。
- [ ] `<FlowRecordLink>` 支持 `variant="plain" | "chip"`，hover 反馈灰阶、cursor-pointer。
- [ ] 关键词审查页「流水行」列 `#{flow_record_id}` 可点击 → 弹窗显示原始↔标准对照。
- [ ] AI 分析页关联记录 chip `#{rid}` 可点击 → 同弹窗（chip 视觉保留）。
- [ ] 弹窗 `max-w-3xl`，双栏各自 `max-h-[60vh]` 滚动；原始 20+ cells 时左侧滚、标准化固定。
- [ ] 弹窗 loading 态「加载中…」；recordId 不存在显示「该流水记录不存在或已删除」。
- [ ] TanStack Query 缓存：同一条记录重复点不重发请求（看 Network）。
- [ ] 单色全程合规：无任何彩色，hover/状态全灰阶。
- [ ] `npm run typecheck` + `npm run lint` 通过；后端 `pytest` 相关测试通过。

## 参考文件（项目内部）

- `frontend/src/routes/__authenticated/tasks/$id/clean.tsx:673`（RawVsStandardCompare 原始实现）
- `frontend/src/routes/__authenticated/tasks/$id/keyword-review.tsx:307`（接入点 1）
- `frontend/src/routes/__authenticated/tasks/$id/analyze.tsx:434`（接入点 2）
- `frontend/src/components/ui/dialog.tsx`（Dialog 组件）
- `frontend/src/lib/api.ts:470`（FlowRecordItem 类型）/ `:510`（listTaskRecords 范式）
- `frontend/src/hooks/use-records.ts`（records hooks 范式）
- `backend/app/routers/tasks.py:903`（list_task_records，新端点参考）/ `:880`
  （`_record_response` 序列化复用）/ `_load_owned_task`（归属校验复用）
- `backend/app/schemas/review.py`（RecordResponse 模型）
