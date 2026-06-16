# 匹配审查与报告导出服务

## Goal

把原桌面端的匹配审查、审计报告和导出能力迁移为 FastAPI 后端能力，让 Web 端可以对已完成提取的任务执行客户名单匹配，查看匹配明细，生成审计报告，并下载标准化 Excel 或 skills bundle 导出文件。

## What I Already Know

* 总 PRD 要求迁移 `src/core/reviewer.py` + `src/core/matcher.py` 到 `backend/app/services/review_service.py`。
* 总 PRD 要求迁移 `src/llm/audit_agent.py` 到 `backend/app/services/audit_report.py`，支持 narrative 报告生成与 Markdown/HTML/Word 导出。
* 总 PRD 要求迁移 `src/export_flows/` 到 `backend/app/services/export_service.py`，支持标准化 Excel、skills bundle、board 级报告导出。
* 后端已有 `Review`、`ReviewMatch`、`Report`、`Task`、`Document`、`CustomerList`、`CustomerListItem` 模型。
* 后端目前还没有 `reviews.py`、`reports.py` 路由，也没有 `review_service.py`、`audit_report.py`、`export_service.py`。
* 当前任务应复用已实现的 JWT/RBAC 认证依赖，并对任务访问执行 owner/collaborator 权限校验。
* 前端已有任务、客户、分析等页面雏形，但本任务的核心缺口在后端服务和 API。

## Requirements

* 实现匹配算法模块，支持精确匹配、脱敏匹配和可配置阈值的模糊匹配。
* 实现 `ReviewService`：
  * 从任务的已提取/标准化流水数据中读取交易记录。
  * 从客户名单读取客户姓名。
  * 执行匹配并持久化 `reviews`、`review_matches`。
  * 记录匹配类型、命中客户、分数、源记录标识和必要的交易摘要字段。
* 实现审查 API：
  * `POST /api/tasks/{id}/review` 创建并执行审查。
  * `GET /api/reviews/{id}` 获取审查摘要。
  * `GET /api/reviews/{id}/matches` 分页获取匹配明细。
* 实现报告服务：
  * 基于任务、审查摘要和匹配明细生成审计报告内容。
  * LLM 未配置或调用失败时提供可用的规则化 fallback 报告，不阻断核心流程。
  * 持久化 `reports` 记录和报告文件路径。
* 实现报告 API：
  * `POST /api/tasks/{id}/report` 为任务/审查生成报告。
  * `GET /api/reports/{id}` 获取报告元数据和内容。
  * `GET /api/reports/{id}/download` 下载报告文件。
* 实现导出服务：
  * 导出标准化 Excel，包含匹配结果列或匹配详情 sheet。
  * 导出单任务 skills bundle ZIP。
  * 输出文件写入 `backend/data/outputs` 或 `backend/data/reports` 下的任务隔离目录。
* 实现导出 API：
  * `POST /api/tasks/{id}/export/excel`
  * `POST /api/tasks/{id}/export/bundle`
  * `GET /api/exports/{id}/download`
* 所有任务级 API 必须校验当前用户是否有任务访问权限；写入/生成类操作要求 owner、admin 或 write/admin collaborator。

## Acceptance Criteria

* [ ] 无权限访问任务审查、报告、导出 API 返回 403 或 404，不泄露任务数据。
* [ ] 对存在标准化流水和客户名单的任务执行 `POST /api/tasks/{id}/review` 后，数据库产生一条 `Review` 和对应 `ReviewMatch` 明细。
* [ ] 匹配结果支持精确、脱敏、模糊三类，并按精确 > 脱敏 > 模糊优先级记录最佳命中。
* [ ] `GET /api/reviews/{id}/matches` 支持分页返回明细。
* [ ] 报告生成接口能在无 LLM 配置时返回规则化报告，并写入 `Report` 记录。
* [ ] 报告下载接口返回实际文件响应。
* [ ] Excel 导出文件可被 openpyxl 打开，并包含匹配用户/匹配度或匹配详情信息。
* [ ] skills bundle 导出返回 ZIP 文件路径并可下载。
* [ ] 后端测试覆盖匹配算法、审查服务核心流程、权限失败路径和至少一个导出文件可读性检查。
* [ ] 前端 typecheck 不因新增 API 类型或路由引用失败。

## Definition Of Done

* Tests added/updated for matching, review service, report fallback, and export file generation.
* Backend pytest passes for the relevant test suite.
* Frontend typecheck passes if API client/types are touched.
* New routes are registered in `backend/app/main.py`.
* Behavior changes are documented in task notes or specs if new conventions emerge.

## Technical Approach

* Start with backend-only service/API implementation; keep frontend wiring minimal unless needed for type consistency.
* Keep matching logic pure and unit-testable, likely under `backend/app/core/matcher.py`.
* Keep orchestration and database writes in `backend/app/services/review_service.py`.
* Use existing SQLAlchemy async session patterns from current routers.
* Use `StreamingResponse` or `FileResponse` for downloads.
* Prefer local file outputs under configured backend data directories; do not write to legacy `~/.check-yg` locations.
* Treat LLM report generation as optional and resilient: deterministic fallback first, LLM enhancement when configured.

## Decision (ADR-lite)

**Context**: The original desktop implementation writes directly to local Excel/history folders and mixes UI-era assumptions with core matching/report/export logic.

**Decision**: Migrate the core behavior into backend services with database-backed review/report metadata and task-scoped output files. Keep APIs synchronous for this MVP unless long-running behavior proves necessary during implementation.

**Consequences**: This keeps the task small enough to finish before integration, while leaving room for the WebSocket/background-task task to make report/export jobs asynchronous later.

## Out Of Scope

* Full frontend task detail page for viewing review/report/export results, unless a small API client change is required.
* Browser desktop notifications for review/report completion; that belongs to the WebSocket/notification task.
* Multi-task board-level ZIP export unless the single-task export service structure makes it very cheap.
* Full LLM prompt management UI.
* External object storage or cloud file persistence.

## Open Questions

* Confirm MVP surface: backend services/API only, or include frontend task-detail UI integration in this task?

## Technical Notes

* Existing models inspected:
  * `backend/app/models/review.py`
  * `backend/app/models/report.py`
  * `backend/app/models/task.py`
  * `backend/app/models/document.py`
  * `backend/app/models/customer_list.py`
* Existing routers inspected:
  * `backend/app/routers/tasks.py`
  * `backend/app/routers/customers.py`
* Legacy source inspected:
  * `src/core/matcher.py`
  * `src/core/reviewer.py`
  * `src/llm/audit_agent.py`
  * `src/export_flows/flow_export.py`
  * `src/export_flows/skill_export.py`
  * `src/export_flows/board_skill_export.py`
* Total PRD references:
  * `PRD_WEB_SPLIT.md` sections for matching/reports/export and API design.
