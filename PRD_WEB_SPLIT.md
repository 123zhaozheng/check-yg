# Check-YG Web 产品需求文档（PRD）

## 项目背景

`check-yg` 是一款面向企业审计场景的 **员工-客户金额往来审计系统**。当前主分支为 PyQt5 桌面应用，核心能力包括：

- 从 PDF、Excel、DOCX 中智能提取银行/支付流水表格
- 通过 LLM 判断流水表格、提取文档画像、标准化流水记录
- 将客户名单与流水对手方进行精确/脱敏/模糊匹配
- 生成 LLM 审计报告与 skills bundle 导出

本次重构目标：在独立分支上将桌面应用改造为 **前后端分离的 Web 应用**，保留并优化核心流水解析逻辑，引入完整的 RBAC 权限与任务协作能力，采用全新的 Web 技术栈。

---

## 目标与范围

### 总体目标

- 建立清晰的前后端分离目录：`web/` 前端、`backend/` 后端。
- 后端使用 **FastAPI + Python 3.13 + uv**，保留并提升所有核心审计能力。
- 前端使用 **React Router + shadcn/ui（b0 preset）**，严格对齐设计规范。
- 支持异步任务 + WebSocket 实时通知 + 浏览器桌面通知。
- 支持 RBAC 权限管控与任务协作者邀请。

### 不做范围

- 暂不做多租户/多组织（单租户多用户，预留扩展）。
- 暂不做外部第三方登录（OAuth）。
- 暂不做真正的付费/订阅系统。

---

## 关键决策

| 决策项 | 选择 | 说明 |
|--------|------|------|
| 后端范围 | 完整保留 + 优化拔高 | 提取、匹配、报告、导出全部迁移为 Web API |
| 前端页面 | 全部对齐 | 7 张 UI 图对应页面均实现，并与后端能力同步 |
| 任务交互 | 异步 + WebSocket 推送 | 提交任务后用户可离开，完成后实时通知 |
| 存储 | SQLite + 本地文件 | SQLite 存元数据；上传文件、输出 Excel 落盘 |
| 认证 | JWT + RBAC | 角色：admin、auditor、viewer；管理员创建账号 |
| 任务协作 | 邀请协作者 | 只读 / 可编辑 / 任务管理员 |
| 注册 | 管理员创建 | 登录页仅用于登录，无开放注册 |
| 圆角风格 | 严格按设计规范 | 输入框 6px、卡片 8px、弹窗 12px |
| Python 版本 | 3.13+ | 不兼容旧版本 |
| 流程管理 | Trellis Workflow | 分 phase 推进 |

---

## 目录结构

```
check-yg/

├── backend/                   # 后端 FastAPI
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # SQLite 连接与模型基类
│   │   ├── models/            # SQLAlchemy 模型
│   │   │   ├── user.py
│   │   │   ├── role.py
│   │   │   ├── task.py
│   │   │   ├── document.py
│   │   │   ├── customer_list.py
│   │   │   ├── collaborator.py
│   │   │   └── setting.py
│   │   ├── schemas/           # Pydantic v2 Schema
│   │   ├── routers/           # API 路由
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── tasks.py
│   │   │   ├── documents.py
│   │   │   ├── customers.py
│   │   │   ├── reviews.py
│   │   │   ├── reports.py
│   │   │   ├── analytics.py
│   │   │   └── settings.py
│   │   ├── services/          # 业务逻辑
│   │   │   ├── extraction/    # 流水提取流水线
│   │   │   │   ├── scanner.py
│   │   │   │   ├── extractor.py
│   │   │   │   ├── checkpoint.py
│   │   │   │   └── progress.py
│   │   │   ├── review_service.py
│   │   │   ├── audit_report.py
│   │   │   ├── export_service.py
│   │   │   └── notification_service.py
│   │   ├── core/              # 从原 src/core 迁移并优化
│   │   ├── llm/               # 从原 src/llm 迁移并优化
│   │   ├── parsers/           # 从原 src/parsers 迁移并优化
│   │   ├── auth/              # JWT、RBAC、权限校验
│   │   │   ├── jwt.py
│   │   │   ├── dependencies.py
│   │   │   └── permissions.py
│   │   └── websocket/         # WebSocket 连接与消息推送
│   │       ├── manager.py
│   │       └── events.py
│   ├── data/                  # 运行时文件（gitignored）
│   │   ├── uploads/
│   │   ├── outputs/
│   │   └── reports/
│   └── tests/
├── web/                       # 前端 React Router
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── app/
│   │   ├── root.tsx
│   │   ├── routes/
│   │   │   ├── login.tsx
│   │   │   ├── dashboard.tsx
│   │   │   ├── tasks.tsx
│   │   │   ├── tasks.new.tsx
│   │   │   ├── tasks.$id.tsx
│   │   │   ├── customers.tsx
│   │   │   ├── analytics.tsx
│   │   │   ├── templates.tsx
│   │   │   ├── prompts.tsx
│   │   │   ├── logs.tsx
│   │   │   ├── settings.tsx
│   │   │   └── users.tsx
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── sidebar.tsx
│   │   │   │   ├── topbar.tsx
│   │   │   │   └── shell.tsx
│   │   │   ├── ui/            # shadcn 组件
│   │   │   ├── tasks/
│   │   │   ├── customers/
│   │   │   └── dashboard/
│   │   ├── hooks/
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── websocket.ts
│   │   │   └── utils.ts
│   │   ├── types/
│   │   └── styles/
│   │       └── globals.css
│   ├── components.json
│   └── public/
├── README.md                  # 重构后总览
└── .gitignore
```

---

## 后端架构

### 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | FastAPI |
| Python | 3.13+ |
| 包管理 | uv |
| ORM | SQLAlchemy 2.0 |
| 数据验证 | Pydantic v2 |
| 数据库 | SQLite（本地文件） |
| 认证 | JWT + passlib bcrypt |
| 任务执行 | asyncio background task / Celery（预留） |
| 实时通信 | WebSocket |
| 测试 | pytest + pytest-asyncio + httpx |

### 核心模块说明

#### 1. 提取流水线（`app/services/extraction/`）

从原 `src/core/flow_extractor_v2.py` 迁移并优化：

- **Stage 1（串行）**：扫描文档目录 → 解析表格 → LLM 判断流水表 → 提取文档画像。
- **Stage 2（并行）**：按流水表批量标准化行记录。
- 支持断点续传、暂停、取消、追加目录。
- 进度通过 WebSocket 实时推送。
- 优化点：使用 asyncio + ThreadPoolExecutor 替代原有 threading，提升并发可观测性；Pydantic 校验 LLM 输出。

#### 2. 匹配审查（`app/services/review_service.py`）

从原 `src/core/reviewer.py` + `matcher.py` 迁移：

- 精确匹配、脱敏匹配（如 `张*`）、模糊匹配（Levenshtein）。
- 写入匹配结果到输出 Excel，新增“匹配用户”“匹配度”列。

#### 3. 审计报告（`app/services/audit_report.py`）

从原 `src/llm/audit_agent.py` 迁移：

-  suspicious patterns：夜间交易、短间隔簇、同金额重复、重复对手方。
- 生成 narrative 报告，支持 Markdown/HTML/Word 导出。

#### 4. 导出服务（`app/services/export_service.py`）

从原 `src/export_flows/` 迁移：

- 标准化 Excel 导出
- Skills bundle ZIP 导出
- Board 级报告导出

#### 5. 通知服务（`app/services/notification_service.py`）

- 任务状态变化时调用 WebSocket 推送。
- 浏览器桌面通知通过前端 Notification API 触发，后端提供消息内容。

---

## 前端架构

### 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | React Router v7（framework） |
| 语言 | TypeScript |
| 组件库 | shadcn/ui（b0 preset） |
| 包管理 | pnpm |
| 样式 | Tailwind CSS v4 |
| 图标 | lucide-react |
| 状态 | React Query (TanStack Query) + Zustand |
| 实时通信 | WebSocket + Notification API |
| 图表 | recharts |
| 表格 | @tanstack/react-table |

### 设计系统

严格对齐 `stitch_audit_system_web_ui_spec/audit_precision_interface/DESIGN.md`：

- **颜色**：深色 flagship，背景 `#0A0A0A` / `#131313`，surface 层级从 `surface-container-lowest` 到 `surface-container-highest`。
- **字体**：Inter 主字体，JetBrains Mono 用于数字/代码。
- **圆角**：
  - 输入框/按钮：`6px`（rounded-md）
  - 卡片/容器：`8px`（rounded-lg）
  - 弹窗/对话框：`12px`（rounded-xl）
- **布局**：左侧固定 240px 侧边栏 + 顶部 56px 导航栏 + 主内容区。
- **语义色**：positive `#10B981`，negative `#EF4444`，warning `#F59E0B`。

---

## 数据库模型

### 用户与权限

- `users`：id, username, email, hashed_password, role_id, is_active, created_at, updated_at
- `roles`：id, name, permissions（JSON），description
  - 默认角色：`admin`, `auditor`, `viewer`

### 任务

- `tasks`：id, title, description, owner_id, status, config, created_at, updated_at, completed_at
- `documents`：id, task_id, filename, original_path, status, extracted_tables, flow_tables, error_log, created_at
- `task_logs`：id, task_id, level, message, created_at

### 客户名单

- `customer_lists`：id, name, owner_id, row_count, created_at
- `customer_list_items`：id, list_id, name, notes

### 匹配与报告

- `reviews`：id, task_id, customer_list_id, match_config, status, created_at
- `review_matches`：id, review_id, record_id, customer_name, match_type, score
- `reports`：id, task_id, review_id, format, content_path, created_at

### 协作

- `collaborators`：id, task_id, user_id, role（read / write / admin），invited_by, created_at

### 系统配置

- `settings`：key, value, category, updated_at, updated_by

---

## API 设计

### 认证

- `POST /api/auth/login`：用户名/密码登录，返回 access_token + refresh_token
- `POST /api/auth/refresh`：刷新 access token
- `POST /api/auth/logout`：登出（黑名单可选）
- `GET /api/auth/me`：当前用户信息

### 用户管理（admin）

- `POST /api/users`：创建用户
- `GET /api/users`：用户列表
- `PATCH /api/users/{id}`：修改角色/启用状态
- `DELETE /api/users/{id}`：删除用户

### 任务

- `POST /api/tasks`：创建任务
- `GET /api/tasks`：任务列表（含权限过滤）
- `GET /api/tasks/{id}`：任务详情
- `POST /api/tasks/{id}/run`：启动提取
- `POST /api/tasks/{id}/pause`：暂停
- `POST /api/tasks/{id}/resume`：继续
- `POST /api/tasks/{id}/cancel`：取消
- `POST /api/tasks/{id}/append`：追加目录
- `DELETE /api/tasks/{id}`：删除（仅 owner/admin）

### 文档与文件

- `POST /api/tasks/{id}/upload`：上传文档
- `GET /api/tasks/{id}/documents`：文档列表
- `GET /api/tasks/{id}/records`：标准化流水记录
- `GET /api/tasks/{id}/preview`：提取预览

### 客户名单

- `POST /api/customer-lists`：创建名单
- `GET /api/customer-lists`：名单列表
- `POST /api/customer-lists/{id}/upload`：上传 Excel 导入客户
- `GET /api/customer-lists/{id}/items`：客户列表
- `DELETE /api/customer-lists/{id}`：删除

### 审查匹配

- `POST /api/tasks/{id}/review`：对某任务执行客户名单匹配
- `GET /api/reviews/{id}`：匹配结果详情
- `GET /api/reviews/{id}/matches`：匹配明细

### 报告

- `POST /api/tasks/{id}/report`：生成审计报告
- `GET /api/reports/{id}`：获取报告
- `GET /api/reports/{id}/download`：下载报告

### 导出

- `POST /api/tasks/{id}/export/excel`：导出标准化 Excel
- `POST /api/tasks/{id}/export/bundle`：导出 skills bundle
- `GET /api/exports/{id}/download`：下载导出文件

### 分析

- `GET /api/analytics/dashboard`：工作台统计数据
- `GET /api/analytics/tasks`：任务趋势
- `GET /api/analytics/matches`：命中分析
- `GET /api/analytics/risks`：风险指标

### 设置

- `GET /api/settings`：系统配置
- `PATCH /api/settings`：更新配置（需 admin）
- `POST /api/settings/test-llm`：测试 LLM 连接
- `POST /api/settings/test-mineru`：测试 MinerU 连接

### 协作

- `POST /api/tasks/{id}/collaborators`：邀请协作者
- `GET /api/tasks/{id}/collaborators`：协作者列表
- `PATCH /api/tasks/{id}/collaborators/{user_id}`：修改权限
- `DELETE /api/tasks/{id}/collaborators/{user_id}`：移除协作者

---

## WebSocket 设计

### 连接

- 路径：`/ws`
- 认证：连接时携带 `access_token` query param 或 header。
- 建立连接后，服务器返回 `connection_id` 和 `status`。

### 订阅

- 客户端发送 `{"type": "subscribe", "task_id": "..."}` 订阅指定任务。
- 客户端发送 `{"type": "subscribe_user"}` 订阅用户级别的全局通知。

### 消息类型

| 类型 | 方向 | 说明 |
|------|------|------|
| `task_progress` | S → C | 任务进度：`{task_id, percent, stage, message}` |
| `task_log` | S → C | 实时日志：`{task_id, level, message, timestamp}` |
| `task_completed` | S → C | 任务完成：`{task_id, status, summary}` |
| `notification` | S → C | 系统通知：`{title, body, type}` |
| `ping` | C → S | 心跳 |
| `pong` | S → C | 心跳响应 |

### 浏览器桌面通知

- 前端通过 `Notification.requestPermission()` 获取权限。
- 当收到 `task_completed` 或 `notification` 时，如果页面不在前台，调用 `new Notification(...)`。

---

## 页面清单

| 页面 | 路由 | 说明 | 来源 |
|------|------|------|------|
| 登录 | `/login` | 用户名密码登录，深色居中卡片 | check_yg_web_1 |
| 工作台 | `/dashboard` | 统计卡片、最近任务、实时活动流 | check_yg_web_2 |
| 任务列表 | `/tasks` | 搜索、筛选、分页、状态标签 | check_yg_web_4 |
| 新建任务 | `/tasks/new` | 上传文件、配置参数、触发提取 | 后端能力 |
| 任务详情 | `/tasks/:id` | 进度、日志、预览、匹配、报告 | 后端能力 |
| 客户名单 | `/customers` | 名单卡片、导入、筛选 | check_yg_web_3 |
| 数据分析 | `/analytics` | 图表、趋势、Top 命中、风险指标 | check_yg_web_6 |
| 模板 | `/templates` | 审计模板管理 | UI 导航 |
| 提示词 | `/prompts` | LLM 提示词管理 | UI 导航 |
| 日志 | `/logs` | 系统运行日志 | UI 导航 |
| 设置 | `/settings` | MinerU、LLM、系统配置 | check_yg_web_5 |
| 用户管理 | `/users` | 管理员创建/管理用户 | RBAC 需求 |
| 用户资料 | `/profile` | 当前用户信息与登出 | UI 导航 |

---

## 阶段计划（Trellis Workflow）

### Phase 1: 基础设施与架构搭建

1. 切出 `feat/web-split` 分支。
2. 创建 `backend/` 目录结构，初始化 `uv` + `pyproject.toml`。
3. 创建 `web/` 目录，执行 `pnpm dlx shadcn@latest init --preset b0 --template react-router`。
4. 配置 shadcn 主题变量，对齐 `DESIGN.md`。
5. 搭建后端目录：`app/models/`, `app/routers/`, `app/services/`, `app/core/`, `app/llm/`, `app/parsers/`, `app/auth/`, `app/websocket/`。
6. 初始化 SQLite 数据库模型，创建 alembic 迁移（可选）。
7. 定义 Trellis workflow 文件。

**验收标准：** 前后端均可独立启动；数据库可创建表；Trellis 可加载 workflow。

### Phase 2: 后端核心迁移与优化

1. 迁移 `scanner.py` 与各 parser。
2. 迁移并优化 `FlowExtractorV2` → 异步流水线。
3. 迁移 `FlowTableClassifier` / `FlowDataNormalizer` / `DocumentPortraitExtractor`。
4. 迁移 `reviewer.py` + `matcher.py` → `review_service.py`。
5. 迁移 `audit_agent.py` → `audit_report.py`。
6. 迁移 `export_flows/` → `export_service.py`。
7. 引入 background task 执行长时间提取。
8. 实现 WebSocket 进度推送。

**验收标准：** 后端能独立完成“上传文档 → 提取 → 标准化 → 匹配 → 生成报告 → 导出”全流程；单元测试通过。

### Phase 3: 认证与权限系统

1. 实现 JWT 登录/登出/refresh。
2. 实现 bcrypt 密码哈希。
3. 定义 `admin`, `auditor`, `viewer` 角色与权限。
4. 实现管理员创建用户 API。
5. 实现任务所有权与协作者邀请（read / write / admin）。
6. 实现任务权限校验 middleware。

**验收标准：** 无 JWT 访问受保护 API 返回 401；无权限访问任务返回 403；协作者可见任务。

### Phase 4: 前端页面实现

1. 实现布局组件：Sidebar、Topbar、Command Palette、Theme Toggle。
2. 登录页。
3. 工作台 Dashboard。
4. 任务列表页。
5. 新建任务/提取页。
6. 任务详情/预览页（含 WebSocket 进度）。
7. 客户名单页。
8. 匹配结果页。
9. 报告页。
10. 设置页。
11. 数据分析看板。
12. 用户管理页。
13. 任务协作者邀请 UI。

**验收标准：** 所有页面存在且与设计图风格一致；导航、路由、状态管理正常。

### Phase 5: 集成、测试与收尾

1. 前后端联调：上传 → 提取 → 预览 → 匹配 → 报告。
2. 浏览器桌面通知。
3. 后端 pytest 测试。
4. 前端构建与 lint。
5. 编写 README 与架构文档。
6. 清理旧 PyQt 代码（可选保留 `legacy/`）。

**验收标准：** 完整流程可在一个浏览器会话中跑通；测试全部通过；README 完整。

---

## 验收标准

### 功能验收

- [ ] 用户可通过登录页进入系统。
- [ ] 管理员可创建用户并分配角色。
- [ ] 用户可创建任务、上传文档、触发提取。
- [ ] 任务运行时用户可离开页面，完成后收到 WebSocket + 浏览器通知。
- [ ] 用户可在任务详情页实时查看进度、日志、预览结果。
- [ ] 用户可上传/管理客户名单，并对任务执行匹配。
- [ ] 用户可查看匹配结果、生成并下载审计报告。
- [ ] 用户可导出标准化 Excel 和 skills bundle。
- [ ] 任务创建者可邀请协作者，并设置只读/可编辑/管理员权限。
- [ ] 设置页可配置 MinerU、LLM 参数并测试连接。

### 非功能验收

- [ ] 前端严格对齐设计规范（颜色、字体、圆角）。
- [ ] 后端使用 Python 3.13+，通过 `uv` 管理依赖。
- [ ] 前后端目录清晰分离，无交叉依赖。
- [ ] 所有核心流水线逻辑有测试覆盖。
- [ ] Trellis workflow 定义完整，可跟踪各 phase 进度。

---

## 风险与依赖

| 风险 | 缓解措施 |
|------|----------|
| LLM 调用不稳定 | 保留重试、超时、fallback 机制；配置可调整 |
| 大文件 PDF 解析慢 | 支持 MinerU 本地/云端；WebSocket 进度让用户感知 |
| 多用户并发任务 | 后台任务隔离；文件路径按 task_id 隔离 |
| WebSocket 连接断开 | 前端自动重连；任务状态以 DB 为准 |
| 权限边界复杂 | 早期编写权限测试；任务级 middleware 统一校验 |

---

## 附录：原项目核心文件映射

| 原文件 | 新位置 | 说明 |
|--------|--------|------|
| `src/core/flow_extractor_v2.py` | `backend/app/services/extraction/extractor.py` | 主流水线 |
| `src/core/scanner.py` | `backend/app/services/extraction/scanner.py` | 文档扫描 |
| `src/core/checkpoint_manager.py` | `backend/app/services/extraction/checkpoint.py` | 断点管理 |
| `src/core/progress_manager.py` | `backend/app/services/extraction/progress.py` | 进度报告 |
| `src/core/matcher.py` | `backend/app/core/matcher.py` | 匹配算法 |
| `src/core/reviewer.py` | `backend/app/services/review_service.py` | 匹配执行 |
| `src/llm/flow_table_classifier.py` | `backend/app/llm/classifier.py` | 表格分类 |
| `src/llm/data_normalizer.py` | `backend/app/llm/normalizer.py` | 数据标准化 |
| `src/llm/document_portrait.py` | `backend/app/llm/portrait.py` | 文档画像 |
| `src/llm/audit_agent.py` | `backend/app/services/audit_report.py` | 报告生成 |
| `src/parsers/*.py` | `backend/app/parsers/*.py` | 文档解析器 |
| `src/config.py` | `backend/app/config.py` | 配置管理 |
| `main.py` | `web/` + `backend/app/main.py` | 拆分为前后端入口 |

---

*文档版本：v1.0*  
*日期：2026-06-15*  
*分支：feat/web-split*
