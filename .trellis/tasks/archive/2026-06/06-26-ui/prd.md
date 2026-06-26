# 精简前端UI中过度的技术性说明文案

## Goal

前端关键词库、审计维度页把内部规格式说明（"卡片 = 卡片名 + 风险等级…"、"维度 = purpose + steps + judgment + severity；后端按固定模板拼成 prompt 存库"）直接当 UI 文案展示，对最终用户毫无意义且显得杂乱。清掉这类开发视角的规格话术，只保留对用户真正有用的操作提示（导入表头格式）。

## Decision (ADR-lite)

**Context**：5 处用户可见文案混在两个页面里，其中部分（导入表头）对用户有用、部分（规格式"X=A+B+C"、prompt 拼接、串行跑）纯开发视角。
**Decision**：采用方案1「整段删除」——副标题/PageHeader 说明整块删掉；导入弹窗仅保留"表头规范：卡片名称,关键词,风险等级,备注"一句，其余规格话术删。
**Consequences**：页面更干净；不损失任何操作必需信息（导入仍能看到列名要求）。admin 编辑表单的字段 label 不动（见 Out of Scope）。

## Requirements

- 删除/精简以下 4 处用户可见文案：
  1. `keyword-library.tsx:107-110` — "关键词卡片" 标题下的整段副标题 `<p>` 删除。
  2. `keyword-library.tsx:567-571` — 导入弹窗说明改为仅保留「表头规范：卡片名称,关键词,风险等级,备注。」一句，删掉"一行一个关键词；…合并追加去重…风险等级合法值…"等规格话术。
  3. `audit-dimensions.tsx:77` — `PageHeader` 去掉 `description` prop（prop 可选，`{description && …}`，去 prop 即不渲染）。
  4. `audit-dimensions.tsx:124-127` — "审查维度卡片" 标题下的整段副标题 `<p>` 删除。

  （第二轮：PageHeader H1 标题下的 description，用户追加）
  5. `index.tsx:39` — 工作台 PageHeader 去掉 `description="实时审查进展与待办队列。"`（保留 title + actions）。
  6. `tasks/index.tsx:102` — 审查任务 PageHeader 去掉 `description="检索、筛选并进入历史审查任务。"`（保留 title + actions）。
  7. `keyword-library.tsx:63` — 关键词库 PageHeader 去掉 description，收成单行 `<PageHeader title="关键词库" />`。
  8. `settings.tsx:76` — 设置 PageHeader 去掉 description，收成单行 `<PageHeader title="设置" />`。

## Acceptance Criteria

- [ ] 上述 8 处开发规格话术/页面说明全部消失（"X = A + B + C"、"拼成 prompt 存库"、"串行跑"、"只读工具"、各页 PageHeader description 等不再出现在用户视野）。
- [ ] 导入 Excel 弹窗仍能看到表头列名（卡片名称,关键词,风险等级,备注）。
- [ ] 两个列表页标题保留、布局不破。
- [ ] `pnpm typecheck` 通过。

## Definition of Done

- 改动仅限上述 2 个文件纯文案。
- typecheck 绿。
- 不涉及逻辑/样式 token/组件结构/后端。

## Out of Scope

- `audit-dimensions.tsx:417` 的表单 label「steps（调哪些只读工具 + 参数）」——属 admin 编辑维度表单的功能性字段名（purpose/steps/judgment/severity 是数据模型本体），与"列表页说明性文案"不同性质，保留。
- `lib/api.ts`、`hooks/*` 代码注释（面向开发者）。
- 后端任何改动。

## Technical Notes

- 仅改 `frontend/src/routes/__authenticated/keyword-library.tsx` 与 `audit-dimensions.tsx`。
- `PageHeader`（`src/components/layout/page-header.tsx`）`description` 为可选 prop，删 prop 安全。
- 无前端 spec 层；最近参考文档为根目录 `PRD_WEB_SPLIT.md`。
