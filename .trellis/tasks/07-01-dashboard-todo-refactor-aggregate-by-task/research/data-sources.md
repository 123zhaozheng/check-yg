# Research: 工作台「待我处理」四类待办的真实数据源

- **Query**: 重构 dashboard `pending_actions` 为"按任务聚合的待办清单"，摸清余额校验审批 / 关键词复核 / AI 分析 / 文档定稿四类的状态字段与动作入口
- **Scope**: internal
- **Date**: 2026-07-01

---

## 当前实现（要被替换的逻辑）

`backend/app/routers/dashboard.py:239-283` 是现有的 `pending_actions` 拼装：
- `review_pending`：`Review.status=="pending"` join Task，owner-scoped，按 `Review.created_at desc` 取前 `_PENDING_ACTIONS_LIMIT=6`（dashboard.py:39, 241-260）。文案 `"待确认告警 · {task_title}"`。
- `report_pending`：凑数分支——只要 `len < 6`，就从 `Report` join Task 取最近 N 条，**没有过滤 `Report.status`**（dashboard.py:262-283），所以已 `final` 的报告也会出现。文案 `"待复核报告 · {task_title}"`。**这就是用户报的 bug：已定稿报告还显示"签发"。**

前端契约：
- `DashboardPendingAction` 类型 `frontend/src/lib/api.ts:322-328`（`id/type/title/task_id`，`type` 注释写死 `"review_pending" | "report_pending"`）。
- 卡片渲染 `frontend/src/routes/__authenticated/index.tsx:178-181`（`onAction` 一律 `navigate(/tasks/${id}/report)`），`PendingActionsCard` 在 `index.tsx:297-357`，按钮文案/主次样式由 `actionLabel`（index.tsx:423-427，`review_pending`→"复核"、`report_pending`→"签发"）和 `solid = type==='review_pending'`（index.tsx:327）决定。

---

## 1. 余额校验审批（balance check）

**没有独立审批模型**——余额校验结果直接复用 `Finding` 状态机。

| 维度 | 值 / 位置 |
|---|---|
| 模型 | `Finding`（`backend/app/models/finding.py:28-86`） |
| "是余额校验产物"标志 | `Finding.source == "balance_check"`（finding.py:75-78；常量 `SOURCE_BALANCE_CHECK` 见 `backend/app/services/audit/balance_check.py:46`） |
| "待审"状态 | `Finding.status == "pending"`（finding.py:56-60，默认 `pending`；三态 `pending/accepted/ignored`） |
| 文档范围 | `Finding.document_id`（finding.py:39-43，balance_check finding 必填；维度 finding 为 NULL） |
| 何时产生"待审" | 清洗跑完时 `run_balance_check` 为每个有余额列的文档产 ≤1 条 `source='balance_check', status='pending'` finding（balance_check.py:164-269，落库在 248-262）。被 `extraction/runner.py` 在标准化收尾时按文档调用。 |
| 何时清掉 | 人工 `PATCH /api/findings/{id}` 改 `status` 为 `accepted`/`ignored`（`backend/app/routers/tasks.py:1370-1404`，校验 owner；`source` 不影响路径）。或重跑 balance_check 时按文档删旧 finding 再算（balance_check.py:231-237，删的是 `source='balance_check'` 且同 `document_id`）。 |
| 列出查询 | `GET /tasks/{id}/findings?source=balance_check`（tasks.py:1323-1367；默认排除 balance_check，必须显式传 `source`）。 |
| 前端入口 | 关键词复核同款——clean 页校验区（`source=balance_check` 单独取，见 tasks.py:1339-1340 注释）。后端无独立"余额校验页"路由，前端通过 findings 列表展示。 |

> 聚合判定草案：某 task 有 `Finding.source=='balance_check' AND Finding.status=='pending'` → 该任务有"余额校验审批"待办。

---

## 2. 关键词复核（keyword review）

| 维度 | 值 / 位置 |
|---|---|
| 模型 | `KeywordHit`（`backend/app/models/keyword.py:113-173`）；状态常量 `HIT_PENDING/CONFIRMED/IGNORED`（keyword.py:48-51） |
| "待复核"状态 | `KeywordHit.status == "pending"`（keyword.py:153-157，默认 `HIT_PENDING`） |
| 何时产生 | 用户点"开始审查" → `POST /tasks/{id}/keyword-review/run`（`backend/app/routers/tasks.py:1561-1591`），逐行×逐词三层匹配后入库，新命中默认 `pending`。重跑先删该 task 全部旧命中再插（tasks.py:1572-1573 注释）。 |
| 何时清掉 | `PATCH /tasks/{id}/keyword-review/hits/{hit_id}` 改 `status` 为 `confirmed`/`ignored`（tasks.py:1638-1679，校验值限 `confirmed/ignored/pending`）。或重跑审查（整 task 删旧重算）。 |
| 列出查询 | `GET /tasks/{id}/keyword-review/hits?status=pending`（tasks.py:1594-1635）。 |
| 是否跑过 | `task.config.last_keyword_review_at`（tasks.py:1578 写入）。无此键 = 从没跑过关键词审查。 |
| 前端入口 | `/tasks/:id/keyword-review`（`frontend/src/routes/__authenticated/tasks/$id/keyword-review.tsx:35`）。状态筛选 tab `"pending" → "待处理"`（keyword-review.tsx:43）。 |

> 聚合判定草案：某 task 存在 `KeywordHit.status=='pending'` → "关键词复核"待办。注意：没跑过审查（无 `last_keyword_review_at`）算不算"待办"是产品决策点——目前无命中行可显示，倾向"不算"（除非产品想推用户去跑审查）。

---

## 3. AI 分析（analyze）

"待办"在这里有**两种可能语义**，需产品确认：

| 维度 | 值 / 位置 |
|---|---|
| 模型 | `Finding`（维度产物，`Finding.source IS NULL` 或 `!='balance_check'`，见 tasks.py:1351-1356）+ `AuditConversation`（追问会话，`backend/app/models/audit_conversation.py:22-51`）+ `AuditDimension`（维度定义，`backend/app/models/audit_dimension.py:48-113`） |
| 是否在跑 | `task.config.last_analysis_summary.status == "running"`（前端派生 `isRunning`，`frontend/src/routes/__authenticated/tasks/$id/analyze.tsx:66-73`）；后端 `analysis_service.AnalysisService.is_running(task_id)`（`backend/app/services/audit/analysis_service.py:58`） |
| 是否跑过 | `task.config.last_analysis_at`（analysis_service.py:95, 220 写入；analyze.tsx:66/71 读取；未分析时缺省）。 |
| "待审" finding | `Finding.source IN (NULL,'rule') AND Finding.status=='pending'`（finding 三态同余额校验）。重跑只删 `status='pending'` 的 finding，保留 accepted/ignored（tasks.py:1292-1294、analysis_service.py:90）。 |
| 何时产生 | `POST /tasks/{id}/analyze`（tasks.py:1281-1320）→ 后台串行跑 enabled 维度 → 每维度产 finding（默认 `pending`）。enabled 维度数 = `AuditDimension.enabled==True` 计数（tasks.py:1306-1313）。 |
| 何时清掉 | `PATCH /api/findings/{id}` 改 `accepted/ignored`（同 §1，tasks.py:1370-1404）。 |
| 列出查询 | `GET /tasks/{id}/findings`（默认排除 balance_check，tasks.py:1323-1367）。 |
| 前端入口 | `/tasks/:id/analyze`（`frontend/src/routes/__authenticated/tasks/$id/analyze.tsx`，Route 在 line 35-50）。 |

**两种"待办"语义（产品决策点）**：
- (a) **从没跑过分析**（无 `last_analysis_at`）→ 推用户"开始分析"。但任务可能根本不需要 AI 分析（例如只跑关键词复核就出报告）。
- (b) **分析跑完、有 `pending` 维度 finding 等人复核**（`Finding.source!='balance_check' AND status='pending'`）→ 这与"待确认告警"语义重叠。

> 聚合判定建议：(b) 更贴近"待我处理"——和余额校验审批对称（都是 finding pending）。若产品要 (a)，需额外界定"任务该跑分析"的触发条件（目前代码无此判定）。

---

## 4. 文档定稿（report finalize）

| 维度 | 值 / 位置 |
|---|---|
| 模型 | `Report`（`backend/app/models/report.py:11-53`） |
| status 取值 | `draft / generating / generated / failed / final`（report.py:21-29 注释；`final` = 整报告只读）。**注意：旧报告/历史数据可能无 status 列值，`getattr(report,'status','draft')` 兜底（reports.py:500）。** |
| "待定稿"标志 | `Report.status IN ('draft','generated')`（即生成完毕但未 `final`）。`generating` 表示还在后台填章、不算"待定稿"；`failed` 同理不应进待办。 |
| 何时产生 | `POST /tasks/{id}/report`（`backend/app/routers/reports.py:154-208`）建 `generating` 报告 + 8 空章，后台逐章填 → `generated`。此时即可定稿。 |
| 何时清掉 | `POST /reports/{id}/finalize`（reports.py:432-467）：`report.status='final'`，并把 `task.status` 推到 `completed` + 写 `task.completed_at`（reports.py:444-457）。写操作守卫 `_ensure_draft` 在 `final`/`generating` 时返 409（reports.py:93-105）。 |
| 与 Task 终态联动 | 报告定稿 = 业务终态，`task.status` 由 `analyzing`→`completed`（reports.py:445-450；dashboard.py:114-116）。所以 **`Task.status=='completed'` 等价于"已定稿"**（completed 仅此处设置，见下附录）。 |
| 最新报告子查询 | dashboard.py:148-154 的 `_LATEST_REPORT_STATUS`（correlated subquery，按 `created_at desc` 取最新 Report.status）；tasks.py:54-63 有同名模式。 |
| 前端入口 | `/tasks/:id/report`（dashboard `onAction` 已指这里，index.tsx:181）。 |

> 聚合判定草案：某 task 最新 `Report.status IN ('draft','generated')` → "文档定稿"待办。**关键修复点**：当前 report_pending 分支无 status 过滤（dashboard.py:265-274），必须加 `Report.status.in_(...)` 且排除 `final`，才能消除"已定稿还显示签发"的 bug。也要排除 `generating`/`failed`。

> 边界：一个 task 理论上可能有多条 Report（reports.py:171-180 取最新一条）。聚合时应看最新一条的状态。

---

## 附录 A：Task.status 全部取值与流转

声明在 `backend/app/models/task.py:21-25`（注释 `draft/running/paused/completed/failed/cancelled`），实际代码还用到 `analyzing`。

| status | 何时置入 | 位置 |
|---|---|---|
| `draft` | 建任务默认值 | task.py:23；tasks.py:343, 393 |
| `running` | start / append / resume | tasks.py:513, 564, 616 |
| `paused` | pause | tasks.py:598 |
| `cancelled` | cancel | tasks.py:634 |
| `failed` | append 出错 / runner 判失败 | tasks.py:580；runner.py:283 |
| `analyzing` | 标准化成功收尾（runner.py:283：无 failed_documents/errors → analyzing）。**task.py 注释里没列，但 dashboard/tasks 路由都按 first-class 用**（dashboard.py:35, 117；tasks.py test fixture 也用） | runner.py:283, 301 |
| `completed` | **仅** 报告定稿时设置（reports.py:448-450）。语义 = "报告已定稿"，不是"任务跑完" | reports.py:448-450 |

"进行中"集合 = `("draft","running","paused","analyzing")`（dashboard.py:35）。`completed/failed/cancelled` 不属进行中。

---

## 附录 B：相关模型字段速查

**Task**（task.py:12-53）：`id, title, description, owner_id, status, config(jsonb), completed_at, employee_name, employee_id, department, audit_start, audit_end, expected_channels(jsonb), archived(bool)` + TimestampMixin(`created_at/updated_at`)。`config` 是 jsonb，承载运行态：`last_result`、`last_analysis_at`、`last_analysis_summary{status,completed,total,...}`、`last_keyword_review_at`、`active_conversation_id`、`document_folder` 等。

**Review**（review.py:12-32）：`id, task_id, customer_list_id, match_config(jsonb), status(default 'pending'), created_at`。`status` 取值在代码里只见 `pending`（dashboard.py/reviews.py 都只判 pending）；未见显式置 `completed/done` 的地方——`Review.status` 似乎始终停留在 `pending`（review 跑完不改状态，见 reviews.py:35-53 只通知不改 status）。**这是当前 `review_pending` 凑数的根源之一：所有 review 永远 pending。** 重构时若仍要保留"审查复核"类，需确认 Review.status 是否真的会被改。

**Report**（report.py:11-53）：`id, task_id, review_id, format, content_path, status(default 'draft'), created_at` + relationships `chapters/annotations`。status 取值见 §4。

**KeywordHit**（keyword.py:113-173）：`id, task_id, flow_record_id, keyword_card_id, keyword_term_id, match_type, confidence, risk_level, matched_field, matched_snippet, status(default 'pending'), note, created_at, updated_at`。

**Finding**（finding.py:28-86）：`id, task_id, document_id(nullable), type, severity, description, counterparty, amount, confidence, status(default 'pending'), comment, dimension_id(nullable), detail_text, evidence_record_ids(jsonb), source(nullable: 'rule'/'balance_check'/None)`。**同时承载"维度分析发现"和"余额校验不符"两类，靠 `source` 区分。**

**AuditConversation**（audit_conversation.py:22-51）：`id, task_id, title, message_history(jsonb), created_at, updated_at`。与"待办"无直接关系（追问会话不产待审项）。

**AuditDimension**（audit_dimension.py:48-113）：`id, name, source('system'/'agent'), purpose, steps(jsonb), judgment, severity, prompt, enabled(bool, agent 沉淀默认 false), created_by, created_at, updated_at`。决定"跑分析会跑几个维度"——`enabled=True` 的才跑。

---

## 附录 C：是否有现成的"按任务聚合"查询可复用

**没有。** 搜遍 `tasks.py` 与 `dashboard.py`，没有任何 `group_by` / 聚合多源的"待办 by task"查询。现有都是单源：
- dashboard.py:190-196 KPI 的 `pending_alerts` = count Review pending（单源）。
- dashboard.py:241-283 pending_actions = Review + Report 两源拼接（非聚合，是 limit 补足）。
- dashboard.py:148-154 / tasks.py:54-63 的 correlated subquery 只取**最新 Report.status**，是按 task 取标量的模式，可借鉴但不是待办聚合。

**重构需要新写聚合**：建议按 task 维度做 4 个存在性子查询（或一次 join + group_by task_id 收集各类 pending 计数），再 filter 出"至少有一类 pending"的 task。可复用的构件：
- `_LATEST_REPORT_STATUS` 子查询模式（dashboard.py:148-154）——按 task 取最新 Report.status。
- owner-scoped + `archived=False` 过滤（dashboard.py:81-85, 167-170）——四类都要套这层可见性。

---

## 附录 D：前端需改的契约点

1. **`DashboardPendingAction` 类型**（api.ts:322-328）：`type` 注释要扩到四类（如 `balance_pending / keyword_pending / analysis_pending / report_pending`）。若新设计要带"该任务有几条 pending / 跳转目标不同"，需扩字段（如 `count?: number`、或新增 `route_hint`）。注意 dashboard 当前 `onAction` 一律跳 `/tasks/{id}/report`（index.tsx:181），四类跳转目标不同（keyword-review / analyze / report / clean 的 findings），**前端 onAction 要按 type 分流**。

2. **`actionLabel` / `solid` 判定**（index.tsx:323-327, 423-427）：当前只有 `review_pending/report_pending` 两个分支，要扩到四类的文案 + 主/次按钮样式。

3. **`useDashboard` hook**（`frontend/src/hooks/use-dashboard.ts`）：纯透传 `DashboardData`，无需改；但若新 payload 字段变了 TS 类型要同步（api.ts ↔ dashboard.py pydantic 模型 dashboard.py:67-78）。

4. **后端 pydantic 模型** `DashboardPendingAction`（dashboard.py:67-72）+ `DashboardData`（dashboard.py:74-78）：若改成"按任务聚合 + 每类计数"，schema 形状要重设计（例如 `pending_actions: list[{task_id, title, items: [{type, count, ...}]}]`），前端类型同步。

5. **"全空则卡片整体隐藏"**：当前卡片在 `actions.length===0` 时显示 `EmptyState`（index.tsx:321-322）。重构后若要"全空就隐藏整张卡"，需要在 index.tsx:178 加 `data && data.pending_actions.length>0`（或后端返 null）的条件渲染——这是前端改动点。

---

## Caveats / 待确认

- **`Review.status` 似乎永远是 `pending`**（reviews.py 跑完 review 不改 status）——当前 `review_pending` 凑数分支可能对所有 review 都命中。重构若要保留"客户名单审查复核"类，需先确认 Review 是否真有"已完成"态，否则该类要么去掉、要么换判定（例如 `ReviewMatch` 是否有人工结论）。**建议向产品确认四类里是否还包含"客户名单审查"。**
- **AI 分析"待办"语义 (a) vs (b)** 见 §3，需产品拍板。
- **没跑过关键词审查算不算待办** 见 §2，需产品拍板。
- 前端"余额校验审批"无独立路由页（与 findings 共用），跳转目标需产品/前端确认（可能跳 clean 页校验区或 analyze 页带 `source=balance_check`）。
