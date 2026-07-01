# 工作台「待我处理」重构 — 按任务聚合的待审清单

## 背景 / 问题

工作台首页右下角「待我处理」卡片（`frontend/src/routes/__authenticated/index.tsx` 的
`PendingActionsCard`）当前是「两类硬塞凑数」：

1. `review_pending` — 来自 `Review.status=="pending"`。但 `reviews.py:35-53` 跑完审查
   **从不修改** `Review.status`，它永远是 `pending` → 该类对所有跑过审查的任务无差别命中，
   是僵尸数据。
2. `report_pending` — 直接塞最近的 `Report`，**没过滤 `status`**
   （`dashboard.py:265-274`）→ 已定稿（`final`）的报告照样进待办，仍显示「签发」按钮。
   这正是用户报的「已定稿为啥还有签发」bug。

用户定性：鸡肋。要求改成「按任务聚合的待审清单」，覆盖四类真实待办，没待办则不显示。

## 目标 / 非目标

**目标**：把「待我处理」重构为「按任务分组的待办清单」，每块=一个任务，块内每类待办
一行、各自一个跳转按钮。没待办则卡片整块隐藏。

**非目标**：
- 不动 `Review` 表/功能/`reviews.py`（只让 dashboard 不再消费它）。
- 不新增任何「已读 / 已处理」标志或新模型列。
- 不动卡片外的其它 dashboard 区块（KPI / 进行中任务表 / 最近报告）。

## 四类待办的数据边界（已逐条确认）

| 类型 key | 中文标签 | 按钮文案 | 后端查询 | 跳转路由 |
|---|---|---|---|---|
| `balance_check` | 余额校验审批 | 审批 | `Finding.source=='balance_check' AND status=='pending'` | `/tasks/:id/clean` |
| `keyword` | 关键词复核 | 复核 | `KeywordHit.status=='pending'` | `/tasks/:id/keyword-review` |
| `analysis` | AI 分析确认 | 确认 | `Finding.source IN (null,'rule') AND status=='pending'` | `/tasks/:id/analyze` |
| `report_finalize` | 文档定稿 | 定稿 | `Report.status=='generated'` | `/tasks/:id/report` |

说明：
- `balance_check` vs `analysis` 是布尔划分：`source=='balance_check'` 归前者，**其余所有**
  pending finding 归后者（防御性兜底，未来加新 source 自动落 AI 分析类）。
- `Report.status` 实际流转：`generating`→`generated`→`final`；`draft` 仅是
  server_default 占位、代码从不写入。待办只算 `generated`（章节生成完、待定稿）。
- 四类的 union 不保证互斥覆盖全任务——某任务任意几类为空就少一行。

## 展示与交互

**卡片结构**（块=任务，块内多行=各类待办）：
```
张三·7月审计
  · 余额校验审批（3 条）   [审批]
  · 关键词复核（5 条）     [复核]
  · AI 分析确认（2 条）    [确认]
  · 文档定稿              [定稿]
```

- **块标题**：任务名（`task.title`）。
- **子行顺序**（固定）：余额校验 → 关键词 → AI 分析 → 文档定稿。
- **计数**：前 3 类显示 `(N 条)`；文档定稿无计数（整篇一个动作）。
- **按钮文案**：按类型——审批 / 复核 / 确认 / 定稿。点击跳各自路由（前端 type→suffix 映射）。
- **角标**：沿用现状，右上角黑色圆角标显示**任务块数**（不是待办条数）。

**排序**：任务块按「最近一次产生待办的时间」降序 = `max(各类最近一条 created/updated_at)`。
`Finding`/`KeywordHit`/`Report` 均有时间戳可取。

**上限**：最多 **8 个任务块**（对齐 `_IN_PROGRESS_LIMIT`）。

**空状态**：四类全空（无任何待办任务）→ **整块隐藏** `PendingActionsCard`，
「最近报告」卡片横向拉伸独占整行（底部 grid 从 2 列变 1 列）。

## 后端契约变更

`DashboardData` 的 `pending_actions` 字段：

- **改名** `pending_actions` → `todos`（强制结构变更、避免新旧混淆）。
- **新结构** `list[DashboardTodoTask]`：

```python
class DashboardTodoItem(BaseModel):
    type: str          # "balance_check" | "keyword" | "analysis" | "report_finalize"
    label: str         # "余额校验审批" | "关键词复核" | "AI 分析确认" | "文档定稿"
    action: str        # "审批" | "复核" | "确认" | "定稿"  (按钮文案)
    count: int | None  # 该类待办数；文档定稿为 None

class DashboardTodoTask(BaseModel):
    task_id: int
    title: str
    items: list[DashboardTodoItem]  # 按固定顺序，仅含有待办的类型
    latest_todo_at: datetime        # 排序键 = max(各 item 最近一条时间)

class DashboardData(BaseModel):
    ...
    todos: list[DashboardTodoTask]  # 按 latest_todo_at 降序，上限 8；全空则 []
```

- 后端**不**给 `route_suffix`（路由是前端职责，避免跨层耦合）；前端维护
  `type → route_suffix` 映射。
- 后端组装逻辑（`dashboard.py`）：对当前用户可见（owner-scoped；admin 全量）+ 未归档
  （`archived=False`）的任务，逐类统计 pending 计数；任一有值则产出一个 `DashboardTodoTask`；
  按 `latest_todo_at` 排序截 8。

## 前端改动

- `use-dashboard.ts`：TS 类型从扁平 `pending_actions` 改为分组 `todos`（`DashboardTodoTask[]`）。
- `index.tsx` 的 `PendingActionsCard`：
  - 改成按任务块渲染（块标题=任务名 + 子行 list）。
  - 子行：`label (count条)` + 按钮（文案=`action`），点击 `navigate({ to: /tasks/:id/<suffix> })`。
  - `type → route_suffix` 映射：`balance_check→clean, keyword→keyword-review,
    analysis→analyze, report_finalize→report`。
  - `todos.length===0` 时整块不渲染；外层 grid 改成「最近报告」独占（`lg:grid-cols-1` 或条件类名）。
  - 移除旧 `actionLabel` helper（`review_pending`/`report_pending` 分支废弃）。

## 可见性 / 权限

沿用 dashboard 现有模型：admin 看全部，普通用户只看 `owner_id==自己` 的任务；所有查询
`archived=False`。

## 验收

1. 任务名下有 pending 余额校验 finding → 块内出现「余额校验审批 (N 条) [审批]」。
2. 关键词/AI 分析/定稿各同理；同一任务多类并存则多行、固定顺序。
3. 报告已 `final` → 不再出现「定稿」/「签发」按钮（修复原 bug）。
4. 跑过客户名单审查的任务不再因 `Review.status` 永远 pending 而冒待办。
5. 某用户名下无任何待办 → 卡片整块消失，「最近报告」拉伸独占。
6. 普通用户只看到自己任务的待办；admin 看到全部。
7. 后端 `lint` / `type-check` / 现有 dashboard 测试通过；前端 `type-check` / `build` 通过。
8. dashboard 单测（若新增/更新）覆盖：四类计数、按任务聚合、排序、上限 8、空列表。

## 风险 / 注意

- `Finding` 与 `KeywordHit` 的 pending 行可能很多；查询走 indexed `task_id`+`status`，
  聚合用 `GROUP BY task_id` + `count`，避免 N+1。
- `latest_todo_at` 取 max 需跨 3 张表（finding/keyword_hit/report）——实现时优先单条
  `SELECT task_id, MAX(updated_at) ... GROUP BY task_id` 再合并，或接受在 Python 侧拼。
- 旧 `pending_actions` 字段名废弃：前端 hook 与组件同步改名，不留兼容字段（内部 API，
  无外部消费者）。
