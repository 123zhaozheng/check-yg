# Journal - zhaozheng (Part 1)

> AI development session journal
> Started: 2026-06-03

---



## Session 1: PDF文件名密码提取规则：括号格式取最后一个括号

**Date**: 2026-06-03
**Task**: PDF文件名密码提取规则：括号格式取最后一个括号
**Branch**: `master`

### Summary

修改 extract_password_from_filename 方法，从'提取文件名开头数字'改为'提取最后一对括号内容'，支持全角半角括号及混配，新增 9 个单元测试

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9c26efe` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 已完成任务新增流水目录功能

**Date**: 2026-06-03
**Task**: 已完成任务新增流水目录功能
**Branch**: `master`

### Summary

在 completed 状态任务的三个点菜单增加'新增流水目录'选项，支持追加新文件夹文档继续处理。document_folder 改为 List[str]，旧数据自动兼容，追加时按路径去重跳过已有文档，空目录弹出提示，复用现有提取/取消流程。trellis-check 修复了 4 个问题（_is_append 重置、并发 worker 防护、死代码、测试类型断言）。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3bd54f1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 设置页新增AI提示词Tab与文档画像注入

**Date**: 2026-06-03
**Task**: 设置页新增AI提示词Tab与文档画像注入
**Branch**: `master`

### Summary

在设置页新增第3个Tab「AI提示词」，内嵌3个子Tab管理提示词；新增DocumentPortraitExtractor从非表格文本提取结构化画像；画像与分类Stage1并行执行；提示词Jinja2模板渲染+变量高亮；金额规则改为始终正数+收支类型严格判断；自动保存+脏标记+恢复默认

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a630e18` | (see git log) |
| `e42fe17` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: 标准化Excel导出增加星期几/休息日列+处理汇总Sheet页

**Date**: 2026-06-05
**Task**: 标准化Excel导出增加星期几/休息日列+处理汇总Sheet页
**Branch**: `master`

### Summary

流水明细Sheet追加星期几(周一~周日)和是否休息日(是/否/未知)两列，纯程序化计算基于transaction_time，使用chinesecalendar库判断法定节假日调休；新增处理汇总Sheet页(文档名称/标准化流水数/状态/失败原因)；ExtractionResult增加per_document_stats跟踪每文档统计

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b766c44` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: 优化画像输入+标准化缺年推断

**Date**: 2026-06-05
**Task**: 优化画像输入+标准化缺年推断
**Branch**: `master`

### Summary

画像输入优化:非表格5000字(可配置)+全量表4行预览(硬编码)+触发条件放宽(有表格即可);画像提示词强调年份提取;标准化提示词增加缺年推断规则(信用卡跨年场景)

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7e8e471` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: Onboarding: join Trellis project

**Date**: 2026-06-15
**Task**: Onboarding: join Trellis project
**Branch**: `feat/web-split`

### Summary

Completed joiner onboarding task 00-join-zhaozheng; learned Trellis workflow, runtime mechanics, and project conventions.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1ea5d3a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Web-Split Phase 1: 基础设施完成

**Date**: 2026-06-15
**Task**: Web-Split Phase 1: 基础设施完成
**Branch**: `feat/web-split`

### Summary

完成 Phase 1 基础设施搭建：1) web-infra: 修复 9 个 shadcn 组件导入问题，添加前端基础设施（API/WebSocket/Auth hooks）；2) backend-infra: FastAPI 入口、配置管理、12 张数据库模型、Pydantic schemas。所有验收标准通过。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bf6c1d6` | (see git log) |
| `6e63285` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Review export backend APIs

**Date**: 2026-06-16
**Task**: Review export backend APIs
**Branch**: `feat/web-split`

### Summary

Implemented backend review matching, report generation, Excel and skills bundle export APIs with SQLAlchemy models, permissions, tests, and backend spec contracts.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c6ede60` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: WebSocket notifications

**Date**: 2026-06-16
**Task**: WebSocket notifications
**Branch**: `feat/web-split`

### Summary

Implemented authenticated WebSocket notifications for review, report, and export completion; wired frontend toast feedback and added focused backend tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d2d7e36` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: B1+B2 基建并行：pg迁移+pydantic-ai+cookie鉴权+静态挂载 / frontend栈+单色设计系统+布局壳

**Date**: 2026-06-22
**Task**: B1+B2 基建并行：pg迁移+pydantic-ai+cookie鉴权+静态挂载 / frontend栈+单色设计系统+布局壳
**Branch**: `feat/web-split`

### Summary

智行卫士全流程交付的 B1(后端基建) + B2(前端基建) 两个 P0 任务并行完成。B1：SQLite→PostgreSQL(docker pg16)+Alembic baseline(13表,JSONB+with_variant双方言)+鉴权cookie化(httpOnly+SameSite=Strict,login/refresh/me/logout,header兼容过渡)+pydantic-ai v1.107.0替换三LLM模块(agent_factory模块级单例/OpenAIChatModel+OpenAIProvider/max_retries=3/trust_env=False/base_url强制/v1,三模块提示词逐字搬进instructions且difflib逐字节验证IDENTICAL,types.py三个pydantic output_type保留raw_amount/is_valid/row_index呼应不删减底线,normalizer加output_validator兜底铁规则)+回归parity测试(mock重写断言逐字保留,69测试全过)+FastAPI挂frontend/dist+SPA fallback。B2：新建frontend/纯SPA(Vite+React18+TanStack Router/Query+Tailwind4+lightningcss(chrome108降级oklch/lab/color-mix→rgb)+shadcn风格)+单色设计系统(9级灰阶零彩色双字体)+布局壳(240px侧栏+56px顶栏+#f7f7f8画布)+6Tab路由骨架+Vite proxy /api+/ws+TanStack Query credentials:include+全站中文化；旧web/归档archive/web-legacy(68 git rename)。硬底线全过：Chrome108渲染验证、单色grep验证、提示词逐字保真、清洗不删减、pydantic-ai按官方规范。trellis-check两任务各0违规。另：stitch_设计资产入库、旧sqlite db移除跟踪、backend spec三份从PyQt5/no-database更新到FastAPI+pg+pydantic-ai现状。真实模型回归(ollama qwen2.5:7b normalizer新旧diff)用户明确推迟。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `dec1993` | (see git log) |
| `a8c0f99` | (see git log) |
| `a48bc33` | (see git log) |
| `7bc3bcc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: S1 登录闭环：前端接通 cookie 鉴权 + 401 静默 refresh + 路由守卫 + 退出

**Date**: 2026-06-22
**Task**: S1 登录闭环：前端接通 cookie 鉴权 + 401 静默 refresh + 路由守卫 + 退出
**Branch**: `feat/web-split`

### Summary

S1 登录闭环切片完成。后端 cookie 鉴权 B1 已就绪，S1 纯前端接通：login.tsx 对接 POST /api/auth/login（credentials:include 带 cookie，成功跳 ?redirect 或 /，已登录访问 /login 自动跳 /，错误态改单色深灰底白字小条不用红色）；api.ts 加 401 静默 refresh——遇 401（非 login/refresh 自身）先 POST /auth/refresh，成功重试原请求一次，refresh 失败或仍 401 跳 /login?redirect，模块级 refreshPromise 去重并发 401，NO_REFRESH_ENDPOINTS 防递归；新建 hooks/use-current-user.ts（TanStack Query useCurrentUser + fetchCurrentUser 供 beforeLoad 预取）；__authenticated.tsx beforeLoad 真实守卫（fetchCurrentUser 失败 throw redirect /login?redirect）；__root.tsx RouterContext 加 user；app-shell.tsx 侧栏底部加退出登录按钮（调 /auth/logout → queryClient.clear → 跳 /login）。验收：pnpm typecheck/build 通过，单色 grep 无彩色，trellis-check 0 违规（静默 refresh 防递归/去重/单次重试/端点排除深度追踪通过），端到端 smoke 通过（后端 cookie 闭环 login/me/refresh/logout + 前端代理 5173→8000 + SPA 路由）。硬底线全过：Chrome108、单色、cookie HttpOnly+SameSite=Strict、不污染 master。umbrella 进度 3/10。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8e51e6b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: S2 Dashboard + S3 任务列表新建弹窗 并行闭环

**Date**: 2026-06-22
**Task**: S2 Dashboard + S3 任务列表新建弹窗 并行闭环
**Branch**: `feat/web-split`

### Summary

S2+S3 两个垂直切片并行完成。S3 任务列表+新建任务弹窗：后端 Task 模型加 7 字段(employee_name/employee_id/department/audit_start/audit_end/expected_channels JSONB/archived 布尔)+Alembic 迁移 79b320f02b84+tasks 路由扩筛选(stage/created_after/before/employee_id/archived/search)+分页+archive/unarchive+DELETE 软删(archived=True 呼应不删减底线)+3 新测试；前端任务列表页中文化对齐 stitch(筛选 Tab+日期+防抖搜索+任务表+阶段胶囊灰阶+分页当前页黑底白字)+新建任务弹窗(基础信息+审查范围渠道勾选+取消描边/创建并进入黑底主按钮，提交后跳 /tasks/{id}/import)+单色 Dialog。expected_channels 类型主 agent 从 dict 改 list[str](弹窗传中文渠道名数组，dict 语义不匹配)。S2 Dashboard：后端新建 GET /api/dashboard 聚合接口(4 KPI: active_tasks/monthly_completed/pending_alerts/avg_audit_hours，avg 用 Python 算保证 sqlite/pg 可移植；权限 admin 全看/非 admin 只看 owner；只用现有 Task 字段 employee_id 占位 None)+main.py 仅 +2 行注册；前端 dashboard 页中文化对齐 stitch(4 KPI 卡数值靠字号字重不靠颜色+同比 ↑↓ 灰度不用红绿+灰阶进度条+进行中任务表阶段胶囊+最近报告区+待办区+REFRESH 描边+新建审查黑底主按钮)+useDashboard hook。验收：72 测试过、alembic head、typecheck/build 过、单色 grep 过、E2E smoke 全通(dashboard 4 KPI + create 带新字段 + list 筛选 + archive/unarchive + 软删 204)。trellis-check 两任务各 0 硬底线违规。Chrome108 复核：构建 CSS color-mix 均在 @supports 守护块内且有 hex-alpha/currentColor fallback，108 安全。硬底线全过。umbrella 进度 5/10。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ad21c6e` | (see git log) |
| `55e0762` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
