# WebSocket 与实时通知

## Goal

补齐 WebSocket 实时通知能力，让已登录的 Web 用户可以建立受认证的实时连接，并在审查、报告、导出等后端操作完成时收到结构化通知，为最终前后端联调提供可观察的异步反馈通道。

## What I Already Know

* 后端依赖已包含 `websockets>=16.0`，但 `backend/app/websocket/__init__.py` 目前为空。
* 后端现有路由已实现审查、报告、导出 API，并统一通过 JWT/RBAC 校验任务权限。
* 前端已存在 `web/app/lib/websocket.ts` 和 `web/app/hooks/use-websocket.ts`，默认连接 `/ws` 并把 JWT token 放在 query string。
* 前端页面目前只提供基础导航和页面骨架；通知展示应保持轻量，避免在本任务中扩展完整任务详情页。
* 上一个 review/export 任务明确把浏览器通知和 WebSocket 完成提醒留给本任务。

## Requirements

* 实现后端 WebSocket endpoint：
  * 路径为 `/ws`，与现有前端封装默认值一致。
  * 支持通过 `?token=<jwt>` 鉴权，复用当前 JWT 解析逻辑。
  * 鉴权失败时关闭连接，不建立匿名通知通道。
* 实现连接管理：
  * 按用户 ID 管理活跃连接。
  * 支持同一用户多个浏览器标签页同时连接。
  * 断开连接时清理连接集合，避免保留失效 WebSocket。
* 实现结构化消息格式：
  * 消息包含 `type` 和 `payload`，与前端 `WebSocketMessage` 类型兼容。
  * 后端至少发送 `notification` 类型消息。
  * payload 至少包含事件类型、标题、消息、相关资源 ID、时间戳。
* 在后端操作完成时发送通知：
  * `POST /api/tasks/{id}/review` 完成后通知当前用户审查完成。
  * `POST /api/tasks/{id}/report` 完成后通知当前用户报告完成。
  * `POST /api/tasks/{id}/export/excel` 和 `/export/bundle` 完成后通知当前用户导出完成。
  * 通知发送失败不应使原 API 请求失败。
* 前端接收通知：
  * 复用现有 `useWebSocket` / `WebSocketManager`。
  * 在登录后的 app layout 中建立连接。
  * 对 `notification` 消息提供轻量 UI 反馈，优先使用已有 toast/sonner 依赖。
  * 暴露连接状态，方便联调时确认是否已连接。

## Acceptance Criteria

* [ ] 未提供 token 或 token 无效时，`/ws` 不建立可用连接。
* [ ] 已登录用户可以通过现有前端 token 连接 `/ws`。
* [ ] 同一用户多个连接都能收到该用户触发的通知。
* [ ] 审查完成后，后端向当前用户广播 `review.completed` 通知。
* [ ] 报告完成后，后端向当前用户广播 `report.completed` 通知。
* [ ] Excel / bundle 导出完成后，后端向当前用户广播 `export.completed` 通知。
* [ ] 通知广播异常只记录日志，不改变原 API 成功响应。
* [ ] 前端登录后自动连接 WebSocket，退出登录或卸载布局时断开。
* [ ] 前端收到通知后展示 toast，并保留连接状态提示用于联调。
* [ ] 后端相关测试覆盖鉴权、连接管理、广播容错或消息发送核心逻辑。
* [ ] 前端 typecheck 不因 WebSocket/通知改动失败。

## Definition Of Done

* 后端 WebSocket 路由注册到 `backend/app/main.py`。
* 后端测试覆盖连接管理和通知触发的关键路径。
* 前端复用现有 WebSocket 封装，不新增大型状态管理方案。
* 相关 lint/typecheck/test 命令通过，或明确记录无法运行的原因。

## Technical Approach

* 在 `backend/app/websocket/` 下实现连接管理和通知 schema/helper。
* 在 `backend/app/routers/` 下新增或注册 WebSocket 路由，保持 HTTP API 路由仍走 `/api` 前缀，WebSocket 走根路径 `/ws`。
* WebSocket 鉴权通过 query token 调用现有 JWT decode 能力，再加载用户；不要为 WebSocket 单独发明认证机制。
* 在 review/report/export 路由完成业务服务调用后，调用通知 helper 广播给 `current_user.id`。
* 前端在受保护的 `_app` layout 内调用 `useWebSocket("/ws")`，并在收到 notification 消息时调用 sonner toast。

## Decision (ADR-lite)

**Context**: 前端已经有 WebSocketManager，后端已有同步审查/报告/导出 API。当前目标是让联调阶段可以看到完成事件，而不是把这些 API 全部改成后台 job。

**Decision**: 本任务采用轻量 in-process WebSocket 连接管理和完成后广播。通知只发送给触发当前 API 的用户，消息格式保持 `type + payload`，便于后续扩展为任务协作者广播或持久化通知。

**Consequences**: 实现简单，足以支撑单进程开发和本地联调；多进程部署、离线通知持久化、通知历史列表需要后续引入共享 pub/sub 或数据库表。

## Out Of Scope

* 不把审查、报告、导出改造为异步后台任务队列。
* 不实现通知历史、未读计数、桌面系统通知权限流。
* 不跨进程广播，也不引入 Redis/pub-sub。
* 不新增完整任务详情页或复杂通知中心。

## Technical Notes

* Existing frontend files:
  * `web/app/lib/websocket.ts`
  * `web/app/hooks/use-websocket.ts`
  * `web/app/routes/_app.tsx`
* Existing backend files:
  * `backend/app/main.py`
  * `backend/app/auth/jwt.py`
  * `backend/app/auth/dependencies.py`
  * `backend/app/routers/reviews.py`
  * `backend/app/routers/reports.py`
  * `backend/app/routers/exports.py`
  * `backend/app/websocket/__init__.py`
* Prior task reference:
  * `.trellis/tasks/archive/2026-06/06-15-review-export/prd.md`
