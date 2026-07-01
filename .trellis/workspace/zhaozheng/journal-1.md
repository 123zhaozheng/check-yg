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


## Session 13: S4 数据导入闭环

**Date**: 2026-06-22
**Task**: S4 数据导入闭环
**Branch**: `feat/web-split`

### Summary

S4 数据导入切片闭环。后端：Document 加 channel+size_bytes 字段（Alembic migration a1c3e5f7b9d2）；upload/append-upload 端点加 channel Form 参数 + 预建 pending Document 行；runner._persist_result_documents 改为按 filename 匹配 update（不再 delete+rebuild）+ 无记录文档最终扫为 completed + _mark_failed 把 pending 行翻 failed——修复前端轮询卡死（成功/失败两路）。新增 GET /documents?channel=&include_deleted= 与 DELETE /documents/{id} 软删（status=deleted，不删行，保留不删减硬底线）。前端：import.tsx 完整数据导入页（渠道列表黑竖条+角标/虚线拖拽框/文件表灰阶状态胶囊 Pending/Parsing 转圈/Done/Failed 黑底白字粗体）/TanStack Query 动态 refetchInterval 轮询/失败重试（缓存 File 重传）/api.ts 追加 Document 类型与函数。81 后端测试绿，前端 build+类型检查通过，Chrome108 CSS 复核无裸 color-mix/oklch。check 复核发现并自修 2 个轮询卡死 bug。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c458c5a` | (see git log) |
| `2955902` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 14: S5 清洗标准化闭环（P0 核心底线）

**Date**: 2026-06-22
**Task**: S5 清洗标准化闭环（P0 核心底线）
**Branch**: `feat/web-split`

### Summary

S5 清洗标准化切片闭环，守住两条 P0 硬底线。①不删减：新建 flow_records 表（record_type standard|unparsed|excluded + raw_payload JSONB 原始全部单元格 + status active|restored + exclude_reason）；extractor stage1 classifier 拒绝的表不再 continue 丢弃→整表产出 excluded 记录，stage2 normalizer is_valid=false 行不再丢弃→产出 unparsed 记录（对照 legacy flow_extractor_v2.py L591/604 确认旧行为是丢弃）；runner _persist_flow_records non-append 删 status!=restored 行重写（restored 永不删）append 只插不删，全库唯一 delete 带 status 守护；收支修正 _infer_transaction_type 只对 standard 应用忠实 legacy 六分支；5 接口 records/excluded/restore(标restored不删行)/commit/export(CSV UTF-8 BOM)。②提示词保真：normalizer/classifier/portrait SYSTEM_PROMPT git diff 0 行未动，test_llm_parity 20 项全绿。前端 clean.tsx 完整清洗页单色改造（异常数卡黑底白字粗体禁 #ba1a1a 红，行展开原始↔标准对照 bg-ink-200 浅灰高亮禁彩色diff，左规则面板静态6规则命中数不造，排除项视图 tab 切+捞回+服务端分页）。95 后端测试绿，前端 build+类型检查通过，Chrome108 CSS 复核无裸 color-mix/oklch。check 复核自修 2 bug（CSV source_file 列写 document_id→改 filename；排除项客户端过滤破坏服务端分页→加 record_type query 独立分页）。固定输入+fake LLM 单测验证不删减+字段无丢。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6d54d30` | (see git log) |
| `cf6d025` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: S6 AI 分析骨架闭环

**Date**: 2026-06-22
**Task**: S6 AI 分析骨架闭环
**Branch**: `feat/web-split`

### Summary

S6 AI 分析骨架切片闭环，agent tools 留接口+占位实现。后端：Finding 模型+migration 1d08c3cec268（severity high|medium|low/status pending|accepted|ignored/confidence/全标量无jsonb）；analysis.py agent 骨架遵循 pydantic-ai v1.107.0 conventions——AuditDeps(db,task_id) 传类型给 get_agent（agent_factory 新增 deps_type 参数默认 None 向后兼容，3 legacy 模块不变）、SYSTEM_PROMPT_ANALYSIS 新占位 instructions（非改 legacy）、3 @agent.tool 只读工具（query_transactions/by_counterparty/by_amount_range，RunContext[AuditDeps]+keyword 参数成 JSON schema+docstring 成描述，select FlowRecordRow record_type=standard 只读不改）、ModelMessagesTypeAdapter 序列化往返、message_history 多轮存 Task.config.analysis_chat_history；run_analysis/chat 占位返回不调真实 LLM（避免占位 prompt 产垃圾）+TODO 注释示范真实 agent.run 接入；4 接口 owner-only（POST analyze 占位建finding+写last_analysis_at / GET findings severity+confidence排序 / PATCH /findings/{id} 校验finding.task.owner 403 / POST chat history存回）。前端 analyze.tsx 完整单色分析页（无stitch自创）：顶部分析控制条+灰阶进度条+左侧发现列表风险等级灰阶+形状双编码（高方块黑底白字/中深灰圆角/低浅灰胶囊 禁红黄绿 选中黑竖条）+右侧详情（推理摘要+关联记录+时间分布灰阶bar+置信度灰阶水平条+采纳/忽略/备注三按钮）+底部对话区（AI浅灰底/用户黑底白字气泡+输入框+发送占位回复）。110 后端测试绿（含 test_llm_parity 18 提示词保真 + test_cleaning_no_drop 2 不删减回归 + 10 新增 agent结构introspection/findings排序/owner403/analyze占位/chat history），前端 build+typecheck 通过，Chrome108 CSS color-mix 在 @supports 块内。提示词保真：normalizer/classifier/portrait git diff 0行。不删减：agent tools 只读。check 复核自修 severity 形状双编码（high rounded-none/medium rounded/low rounded-full）。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1876708` | (see git log) |
| `04fa406` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: S7 审查报告闭环

**Date**: 2026-06-22
**Task**: S7 审查报告闭环
**Branch**: `feat/web-split`

### Summary

S7 审查报告闭环完成 (umbrella 8/10→9/10)。后端：新建 ReportChapter/ReportAnnotation 模型 + migration(revises S6 1d08c3cec268) + report_chapter_builder 确定性 6 章拼装(概述/被审查对象/数据范围/异常发现汇总/风险评估/结论建议，聚合 S5 flow_records + S6 findings) + reports.py 章节化生成(幂等)/GET/PATCH章节/单章重生成/拖拽排序/全报告重生成/批注CRUD/定稿接口。定稿只改 Report.status draft→final 软态(不删减)，定稿后所有写操作 409。owner-only 复用 _load_owned_report。前端：report.tsx 三栏单色页(左大纲可拖拽HTML5/中正文行内编辑textarea细虚线框+轻量markdown渲染+异常卡片块/右批注左细灰竖线+浅灰底块禁彩色) + use-report hooks + api.ts 追加。trellis-check 自修2项：异常卡片builder格式与FindingCard触发对齐(原是死代码)+已定稿标签灰阶token对齐。验证：127后端测试绿(+17报告)+pnpm build通过(chrome108)。硬底线守住：Chrome108(9级ink token无裸oklch/lab/color-mix)、单色(批注禁彩色高亮)、不删减(定稿只改软态)、提示词保真未碰、不污染主分支(feat/web-split)。决策：数据源=S6findings+S5flow_records(不动legacy ReviewMatch链路)、独立ReportChapter表、纯文本textarea行内编辑、章节级批注、生成即建6章、重生成占位确定性模板。关键词词库+三层匹配+注入AI/AI聊天改造/富文本/@他人/PDF导出均不做(留后续切片)。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ebf5dfd9` | (see git log) |
| `73cacc1e` | (see git log) |
| `1bd06d26` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: web-4 收尾修复 + LLM 模型卡片按阶段选模型

**Date**: 2026-06-23
**Task**: web-4 收尾修复 + LLM 模型卡片按阶段选模型
**Branch**: `feat/web-split`

### Summary

从「后端无日志」一路追到根因:(1) 日志被 watchfiles/pikepdf/alembic.runtime 噪音淹没 + 启动卡死——_run_alembic_upgrade 在 asyncio 事件循环所在进程跑同步 alembic 会因 fileConfig 重配 logging 与 uvicorn handler 冲突而死锁,改 subprocess.run 起独立子进程跑迁移解决;LLM 失败日志加厚为异常类型+业务后果三件套。(2) 画像生成失败根因实锤:step-3.7-flash 是 reasoning 模型,reasoning token 计入 max_completion_tokens 预算,硬编码 1500 被推理烧光→UnexpectedModelBehavior;更深发现设置页早有 llm.max_tokens 但三模块没读它各自硬编码,设置项是孤儿。(3) 新任务 06-23-llm-model-card:llm_models+llm_model_assignments 两表+迁移+seed,三模块按阶段读卡片(严格优先级 阶段卡片>runtime ll.*>模块兜底),agent_factory thinking 透传(trellis-check 抓到关键 bug:默认 profile supports_thinking=False 会静默丢弃 thinking,改传 OpenAIModelProfile(supports_thinking=True) 让 reasoning_effort 真发到端点+加 HTTP 层回归测试),CRUD/指派 API(admin 鉴权+api_key 脱敏+删被指派返 409),前端「集成与模型」tab,14 新测试。178 tests + alembic head a5b2c0d3e1f8 + frontend build 通过。两任务归档。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4e1e4713` | (see git log) |
| `3a63a3e0` | (see git log) |
| `091dc294` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 18: 关键词库 + 关键词审查阶段 + 删概览 + 清洗规则折叠

**Date**: 2026-06-23
**Task**: 关键词库 + 关键词审查阶段 + 删概览 + 清洗规则折叠
**Branch**: `feat/web-split`

### Summary

新增全局关键词库(左侧导航页,keyword_cards/terms 两表,CRUD+excel 导入合并追加去重+导出,admin 限写)与任务级关键词审查阶段(移植 legacy matcher 三层精确/脱敏/模糊 Levenshtein 阈值70%,只扫 standard 对手名+摘要,手动触发重跑清旧再插,keyword_hits 表+采纳/忽略/备注,不自动喂 AI);删任务概览子 tab(/tasks/:id 重定向到数据导入);清洗页应用规则栏改可折叠默认收起。trellis-check 自修 6 问题含 matcher 模糊层 NameError 真运行时 bug。214 tests / alembic 单 head b7c3d1e4f2a9 / frontend build(chrome108)全过。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `fa2a380f` | (see git log) |
| `07e4cada` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 19: 精简前端UI过度的技术性说明文案 + greenlet依赖修复

**Date**: 2026-06-26
**Task**: 精简前端UI过度的技术性说明文案 + greenlet依赖修复
**Branch**: `feat/web-split`

### Summary

删除关键词库/审计维度/工作台/审查任务/设置页中面向开发者的规格式说明文案（卡片=…、维度=purpose+steps…、各 PageHeader description），仅保留导入Excel表头提示；另修后端缺 greenlet 依赖导致异步 ORM 启动报错。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ad548fa` | (see git log) |
| `d5306b9` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 20: Report generation and export polish

**Date**: 2026-06-28
**Task**: Report generation and export polish
**Branch**: `feat/web-split`

### Summary

Implemented LLM-backed async report generation, constrained markdown rendering for DOCX/PDF exports, frontend polling, fallback behavior, and related regression coverage.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d7d34c8` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 21: 导入流程锁定 + 全局任务搜索跳转

**Date**: 2026-06-30
**Task**: 导入流程锁定 + 全局任务搜索跳转
**Branch**: `feat/web-split`

### Summary

导入页处理中锁定文件添加(前端拦截+Dialog)、useTask running态2s轮询使开始处理按钮自动复位、topbar全局搜索框接入(受控+debounce+下拉跳转)、后端list_tasks search扩展为title/employee_id/employee_name OR。5文件256增3删,后端21测试通过前端tsc通过。gitignore加backend/.tmp。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `8d813681` | (see git log) |
| `48bf2596` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 22: PDF 中文字体修复 + docx 移除 + LLM agent 参数 + 任务状态语义修正

**Date**: 2026-06-30
**Task**: PDF 中文字体修复 + docx 移除 + LLM agent 参数 + 任务状态语义修正
**Branch**: `feat/web-split`

### Summary

1) PDF 中文豆腐块：reportlab 注册 STSong-Light CID 宋体，export_service 11 处 Helvetica 替换。2) 移除已废弃 docx 导出，默认导出改 pdf。3) LLM agent 加 supports_tool_choice_required 参数，AsyncOpenAI max_retries 3→5。4) 任务状态语义修正：runner 标准化完成设 analyzing（不再 completed），completed_at 仅 failed 标记，finalize_report 定稿才推进 task 到 completed；抽出 _derive_stage_label 单一真相源，TaskResponse 暴露 stage，dashboard/任务列表统一用后端 stage，删除前端 stageFromStatus 推断；dashboard 全查询过滤 archived，上次同步改用 dataUpdatedAt + 30s 轮询，list_tasks status_filter 支持逗号分隔多值。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `61c7b49a` | (see git log) |
| `2ec3d794` | (see git log) |
| `9b122c65` | (see git log) |
| `68ef42f7` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 23: AI 分析页状态持久化修复

**Date**: 2026-06-30
**Task**: AI 分析页状态持久化修复
**Branch**: `feat/web-split`

### Summary

修复 /tasks/:id/analyze 页点'开始分析'后切走再切回丢失分析中状态的问题。根因：running 曾为纯本地 useState，组件卸载即销毁。改为派生 isRunning = optimisticRunning || summary?.status==="running"（读后端持久态 task.config.last_analysis_summary.status），导航往返 useTask 重取后自动恢复；并补完成态 taskQuery.refetch()——WS-healthy 时 summary.status 不会被自动刷新，必须 refetch 让后端回填的 finished 落地，否则按钮/进度条卡死。仅前端 analyze.tsx，无后端改动。tsc 通过，check subagent 验证 5 个场景（含 WS-healthy 完成态、导航往返、二次重跑、无循环）全部成立。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d423c87a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 24: 清理 LLM 阶段过时「预留」标记

**Date**: 2026-06-30
**Task**: 清理 LLM 阶段过时「预留」标记
**Branch**: `feat/web-split`

### Summary

ai_analysis/ai_qa/report_generation 三阶段早已接通真实 LLM（analysis.py:146/151、report_agent.py:158 在用 STAGE_AI_ANALYSIS/AI_QA/REPORT_GENERATION），设置页的「（预留，待接入）」标识是过时脏代码。删除范围：前端 settings.tsx 的 STAGE_LABELS.reserved 字段 + 渲染块 + 段落提示；api.ts Stage 注释；后端 llm_model_assignment.py 零引用的 RESERVED_STAGES 死常量 + docstring/注释里「后三个预留/占位」过时措辞。保留 6 个 STAGE_* 常量与 ACTIVE_STAGES（runner.py 运行时在用）。前端 tsc 通过。本次为 inline 清理，无 trellis task，跳过 archive。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3841f554` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 25: 流水号可点击弹窗（原始↔标准化对照）

**Date**: 2026-07-01
**Task**: 流水号可点击弹窗（原始↔标准化对照）
**Branch**: `feat/web-split`

### Summary

关键词审查页流水行列、AI 分析页关联记录 chip 的 #流水号 从纯文本/静态 chip 改为可点击，弹 max-w-3xl Dialog 展示左原始 cells / 右标准化字段对照。新增后端 GET /tasks/{id}/records/{record_id} 单条端点（双 id 防越权），抽 RawVsStandardCompare 为共享组件（清洗页零行为变化复用），新增 FlowRecordLink + useFlowRecord。grill 敲定 8 决策：纯弹窗可下钻不塞摘要、2 处接入、纯查看无操作、单色硬底线、共享组件抽取、finding.id 不动。trellis-check 自修 1 处（plain 下划线改 hover-only）。前端 typecheck + build 通过，后端 57 测试绿。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `aea71c8a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
