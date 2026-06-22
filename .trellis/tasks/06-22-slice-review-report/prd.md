# S7 — 审查报告闭环 (slice-review-report)

垂直切片：把 AI 分析结论汇总成**正式审查报告**，支持章节化、人工复核批注、单章/全报告重生成、定稿只读。父任务 `06-22-zhixing-full-delivery` 第 9 个切片，umbrella 8/10 → 9/10。

## 范围边界（决策对齐结果）

- **数据源**：S6 `findings`（异常发现）+ S5 `flow_records`（标准化记录统计）+ `Task` 基础信息聚合。**不沿用** legacy `Review/ReviewMatch` 客户名单匹配链路（旧 `ReportService`/`reports.py` 保留不动，本轮新报告走新链路）。
- **关键词词库 + 三层匹配 + 注入 AI 分析** → **不纳入 S7**，留作后续独立切片。
- **AI 聊天（S6 chat）后续再改**，S7 不碰。

## 硬底线（不可违反）

1. **Chrome 108 渲染**：构建 CSS 的 color-mix 必须在 `@supports (color:color-mix(in lab,red,red))` 守护块内且有 hex-alpha/currentColor fallback；禁裸写 oklch/lab/color-mix，只用 9 级 ink token。
2. **单色原则**：全站禁彩色，9 级 ink 灰阶；报告正文像黑白年报；批注用左细灰竖线 + 浅灰底块（禁彩色高亮）；定稿用"已定稿"灰阶标签（禁红黄绿）。
3. **不删减精神**：定稿不改章节内容、不删行，只改 `Report.status` 软态（draft→final）；重生成不改旧行，重写 content（content 是可再生的派生数据，非原始记录，不违反不删减——原始记录在 S5 flow_records.raw_payload 已兜底）。
4. **不污染主分支**：全程 `feat/web-split`。
5. **pydantic-ai 规范**：S7 单章重生成是**占位 + 确定性模板**（不接真实 LLM）；若后续接入 agent.run，遵循 deps_type 传类型 / deps 传实例 / message_history / ModelMessagesTypeAdapter。

## 数据模型（决策 2 = 独立 ReportChapter 表）

新增 `ReportChapter` 表 `report_chapters`：
- `id` PK / `report_id` FK→reports.id / `title` String(100) / `content` Text / `order_index` Integer（拖拽排序）/ `generated_at` DateTime
- 关系 `report` back_populates `chapters`。

新增 `ReportAnnotation` 表 `report_annotations`：
- `id` PK / `report_id` FK→reports.id / `chapter_id` FK→report_chapters.id（nullable，章节级批注，决策3）/ `author` String(100) / `content` Text / `resolved` Boolean default false / `created_at` DateTime
- 关系 `report`/`chapter` back_populates `annotations`。

改 `Report` 表：+ `status` String(20) default "draft"（draft | final）。`review_id` 保留 nullable（新链路不用，但不动旧列）。

Alembic migration：revises `1d08c3cec268`（S6 head）→ 新 S7 revision。`migrations/env.py` + `database.py init_db` import 登记 `ReportChapter`/`ReportAnnotation`。

## 后端接口（契约先行）

新建 `backend/app/routers/reports.py` 扩展或新增 report chapter/annotation 接口（沿用 owner-only `_load_owned_task`）：

1. `POST /api/tasks/{task_id}/report` — 生成报告（沿用并改造）：聚合 S5 flow_records 统计 + S6 findings，按 6 章模板确定性拼装，建 1 个 Report（status=draft）+ 6 个 ReportChapter 行（概述/被审查对象/数据范围/异常发现汇总/风险评估/结论建议）。幂等：若该 task 已有 draft 报告则返回已有的（避免重复生成），无则新建。
2. `GET /api/tasks/{task_id}/report` — 取该 task 当前报告 + 章节列表（按 order_index 排序）+ 批注列表。
3. `PATCH /api/reports/{report_id}/chapters/{chapter_id}` — 编辑章节 content（定稿后 409）。
4. `POST /api/reports/{report_id}/chapters/{chapter_id}/regenerate` — 单章重生成（占位确定性模板重新拼装该章，定稿后 409）。
5. `POST /api/reports/{report_id}/chapters/reorder` — 拖拽排序（接收 `[{chapter_id, order_index}]` 批量更新 order_index，定稿后 409）。
6. `POST /api/reports/{report_id}/regenerate` — 重新生成全报告（占位重新拼装所有章节，定稿后 409）。
7. `POST /api/reports/{report_id}/annotations` — 新建批注（chapter_id + content）。
8. `PATCH /api/reports/{report_id}/annotations/{annotation_id}` — 切换批注 resolved 状态。
9. `POST /api/reports/{report_id}/finalize` — 定稿：Report.status→final，章节只读（后续编辑/重生成/批注新建均 409）。
10. `PATCH /api/reports/{report_id}` — 保存草稿（status 维持 draft，可作轻量 autosave 钩子，可选实现，最小化可只返当前状态）。

owner 校验：所有接口通过 `Report.task_id` → `Task.owner_id == current_user.id` 校验（复用 `_load_owned_task` 模式）。

## 报告 6 章模板（确定性拼装，占位）

1. **概述** — 任务标题 / 任务编号 / 状态 / 创建时间 / 审查期间。
2. **被审查对象** — 员工工号 / 姓名 / 部门（来自 Task 字段）。
3. **数据范围** — 文档数 / standard 记录数 / 渠道分布 / 清洗提交时间（来自 flow_records 聚合 + Task.config.cleaning_committed）。
4. **异常发现汇总** — findings 总数 / 按 severity 分组（high/medium/low 计数，灰阶递进描述，禁红黄绿）/ accepted vs ignored vs pending 计数。
5. **风险评估** — high severity findings 列表（标题/金额/对手/AI结论/关联记录入口占位）/ 风险等级灰阶表述。
6. **结论建议** — 模板化建议（有 high finding → 建议重点关注；无 → 建议常规复核）。

每章 `content` 存 Markdown 文本（前端渲染）。异常条目卡片块在第 5 章嵌入。

## 前端（§C5 审查报告页 `/tasks/:id/report`）

替换 `frontend/src/routes/__authenticated/tasks/$id/report.tsx` 占位为完整页：

- **三栏布局**（桌面）：左报告大纲 / 中报告正文 / 右复核批注栏。
- **左·报告大纲**：6 章目录，点击跳转中间正文对应章节（scroll/锚点），可拖拽排序（调 reorder 接口），当前选中章黑底高亮。
- **中·报告正文**：
  - 章节标题粗体大字 + 正文规整排版（黑白年报风）。
  - 第 5 章异常条目以卡片块嵌入（标题/金额/AI结论/关联记录入口占位）。
  - 行内编辑：点段落进入 textarea 编辑态（细虚线框），blur/保存调 PATCH 章节接口。纯文本（决策2），Markdown 渲染展示。
  - 每章「重新生成本章」描边次按钮 + 顶部「重新生成全报告」描边次按钮。
  - 顶部「保存草稿」描边次按钮 + 「提交定稿」黑底主按钮。
  - 定稿后整页只读 + 显示"已定稿"灰阶标签（水印式）。
- **右·复核批注栏**：批注列表（批注人 + 时间 + 文本 + 解决状态灰阶），左细灰竖线 + 浅灰底块（禁彩色）；新建批注（选章节 + 输入文本）；切 resolved 状态。@他人本轮不做。

新增 `frontend/src/hooks/use-report.ts`：useReport（取报告+章节+批注）/ useGenerateReport / usePatchChapter / useRegenerateChapter / useReorderChapters / useRegenerateReport / useAddAnnotation / usePatchAnnotation / useFinalizeReport。`api.ts` 追加对应类型与函数（主体稳定，只追加）。

## 验收

- Chrome 108 渲染正常（color-mix 全在 @supports 守护块内）。
- 报告生成产出 6 章 + 大纲跳转 + 正文黑白年报排版。
- 行内编辑可用（细虚线框 → 保存）。
- 单章重生成 + 全报告重生成（占位确定性）。
- 拖拽排序生效。
- 批注增 + 切 resolved，左细灰竖线 + 浅灰底块禁彩色。
- 定稿后只读 + "已定稿"灰阶标签，编辑/重生成/新建批注均 409。
- 后端：`pytest tests/ -x` 全绿（含新增报告章节/批注/定稿单测）。
- 前端：`pnpm build`（tsc --noEmit + vite build chrome108）通过。

## 不做（避免范围蔓延）

- 关键词词库 + 三层匹配 + 注入 AI 分析（后续切片）。
- AI 聊天改造（S6 chat 占位留着，后续）。
- 富文本编辑器（纯文本 textarea）。
- @他人批注。
- PDF/Word/HTML 报告导出（S8 导出切片）。
- legacy Review/ReviewMatch 链路报告（不动旧 ReportService）。
