# web 导入页与审查子页 4 项修复

## 背景

智行卫士 web 端在使用中暴露 4 个问题,用户要求打包为一个 trellis 任务修复。本任务为纯修复/增强,不涉及 LLM 兼容性(见「验收前置条件」)。

任务目录:`.trellis/tasks/06-23-web-4`

## 硬底线(沿用全项目)

- 前端必须在 Chrome 96 / 108 正常渲染(不引入需要更高版本的能力;hover 弹窗用纯 CSS,不引 radix)。
- 单色设计:9 级 ink token,错误黑白、**不用红色**。
- 清洗「不删减」:本任务不动 flow_records 的保留语义,只加 portrait 持久化与并发限流,不删任何行。
- 不污染 main 分支;本任务在 `feat/web-split` 分支推进。

## 四项修复

### ① 窗栏冗余(最轻)

**现象**:`/tasks/4/clean`、`/tasks/4/analyze` 页顶部出现重复文案——布局壳 `PageHeader`(「2026-06 任务 4」+ 员工工号描述)与子页自带的「面包屑 + h1 + 描述」叠加,「任务4」「清洗与标准化」各出现两次。

**修法(决策 A:只留布局壳)**:
- 删除 `frontend/src/routes/__authenticated/tasks/$id/clean.tsx` 约 152-183 行的整个 `{/* Header */}` div(面包屑 + h1 + 描述)。
- 删除 `frontend/src/routes/__authenticated/tasks/$id/analyze.tsx` 约 95-112 行的整个 `{/* Header */}` div。
- `overview.tsx` 的 `TabPlaceholder`(内嵌 h2+p)若与布局壳 PageHeader 重复,一并删除其标题段。
- **保留**布局壳 `$id.tsx:53-57` 的 `PageHeader` 不动(含现有占位文案,不扩范围接真实任务数据)。子页靠 tab 导航高亮辨位。
- `import.tsx`/`report.tsx`/`export.tsx` 本就无自带 header,不动。

**验收**:clean/analyze/overview 页顶部只有一层标题,无重复「任务N」「子页名」。

### ② 后端日志安静(轻)

**现象**:任务跑起来后台控制台几乎无阶段性日志,看不到 mineru 在解析哪个文件、大模型在做分类/画像/标准化哪一步。

**根因**:(a) backend 未配 `logging.basicConfig`,root logger 默认 WARNING,所有 `logger.info()` 被吞;(b) 后端 `extractor.py` stage1/stage2 关键节点缺中文 info 日志(对比 src 原版少约 20 条)。

**修法(决策 A:开 level + 补关键阶段中文日志)**:
- `backend/app/main.py` 顶部加 `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")`。
- `backend/app/services/extraction/extractor.py` 补中文 `logger.info`:
  - 扫描完成:「扫描完成,共发现 %d 个文档」
  - 阶段1入口:「阶段1开始:逐文档表格识别与流水判定」
  - 每文档:「阶段1处理文档: %s (%d/%d)」
  - mineru 解析完成:「文档 %s 解析完成,抽取到表格 %d 个」
  - 画像开始/完成:「开始提取文档画像: %s」「文档画像提取完成: %s」
  - 阶段2入口:「阶段2开始:流水行标准化(并发=%d)」
  - 完成:「提取完成:%d 条流水,失败文档 %d 个」
- `portrait.py`/`classifier.py`/`normalizer.py` 已有的中文 `logger.info`/`logger.warning` 随 level 解封即生效,不再被吞。
- 日志走控制台 stdout,中文,不落盘、不加 LOG_LEVEL 配置项。

**验收**:启动后端,跑一个任务,控制台能看到上述每一步中文日志,mineru 解析/画像/分类/标准化阶段清晰可辨。

### ③ 数据导入改为手动开始 + 可配并发(最重)

**现状**:`POST /api/tasks/upload`(tasks.py:360)与 `POST /api/tasks/{id}/append-upload`(tasks.py:418)上传完立即 `runner.start()` 自动跑。stage1 串行,stage2 裸 `asyncio.gather` 无并发上限。running 期间上传被 409 拒绝(tasks.py:393)。

**修法**:

**(a) 上传不再自动启动**:
- `create_task_from_upload` / `append_task_from_upload`:去掉 `runner.start()` 调用,只存盘 + 建 Document 行(pending)+ 登记路径。任务状态保持 `draft`(决策:复用 draft,不引入 imported)。
- 复用现有 `POST /api/tasks/{id}/start`(tasks.py:450)作为手动触发入口;允许不带 `document_folder` body,回退到 `config["document_folder"]`(已存)。

**(b) 前端「开始处理」按钮**:
- `import.tsx`:在有 pending 文档且任务非 running 时,显示「开始处理」主按钮,点击调 `POST /tasks/{id}/start`(经新 hook `useStartExtraction(taskId)`)。
- 现有「开始处理」按钮(实为上传入口)文案改为「上传文件」,与新的「开始处理」区分。

**(c) 批循环 + running 时可上传自动接上(决策:批循环)**:
- runner 改为循环:每轮处理当前所有 pending/未处理文件(stage1+stage2),跑完检查队列有没有新上传进来的文件,有则再跑一轮,没有则 `running→completed`。
- `append-upload` 端点去掉 `running` 409 拦截:running 期间允许上传,只存盘 + 建 pending Document 行 + 登记路径到队列,不重启 runner;当前批跑完循环自动接上。
- 队列实现:以 Document 表 `status='pending'` 的行为待处理队列;每轮循环查 pending 文件处理。或以 `task.config` 里的 append_document_folders 列表 + path-aware 去重(沿用现有 append 机制)。

**(d) 并发限流(决策:stage1+2 都并发,两项配置)**:
- `settings_service.py` DEFAULT_SETTINGS 加两项:
  - `extraction.mineru_concurrency`:number,默认 1,category `extraction`,label「MinerU 解析并发」,描述「stage1 文档解析并发数,public mineru 建议保持低值」。
  - `extraction.llm_concurrency`:number,默认 2,category `extraction`,label「大模型并发」,描述「stage2 标准化文档级并发数」。
- `runner.start` 签名加 `mineru_concurrency`/`llm_concurrency` 参数,从 `load_runtime_settings` 读入传入。
- `extractor.py` stage1 串行循环改为受 `asyncio.Semaphore(mineru_concurrency)` 限流的并发(stage1 并发处理文档);stage2 `asyncio.gather` 外包 `asyncio.Semaphore(llm_concurrency)` 限流。
- 默认 1+2 保守起步;实现阶段实测并发 mineru 是否被限流,若被限则维持默认低值。

**验收**:上传后任务不自动跑(draft);点「开始处理」才跑;running 时再拖文件不报 409,跑完当前批自动接上;并发度可在设置页改且生效(控制台日志可见并发数)。

### ④ 文档画像持久化 + hover 弹窗(中)

**现状**:portrait 只存 checkpoint JSON,从未进 DB。Document 表无 portrait 列。前端 `FileRow`(import.tsx:308-391)文件名只有原生 `title`,无 hover 弹窗。项目无 popover/tooltip 组件。

**修法**:

**(a) Document 表加 portrait 列**:
- `backend/app/models/document.py` 加 `portrait: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)`。
- 新 alembic 迁移:down_revision = `b9e7f3a2c1d4`(当前 head),add column `documents.portrait` jsonb nullable。database.py sqlite 路径加匹配的轻量 ALTER TABLE。

**(b) 持久化 portrait**:
- `extractor.py` stage1 生成 portrait 后,经 `ExtractionResult` 带出(per_document_portraits dict 或在 flow_tables item 里携带)。
- `runner.py` `_persist_result_documents` 更新 Document 行时写 `target.portrait = portrait`。

**(c) API 返回 portrait**:
- `DocumentResponse`(tasks.py:674)加 `portrait: Optional[dict] = None`;`_document_response` 填 `portrait=doc.portrait`。
- 前端 `lib/api.ts` `DocumentItem` 加 `portrait?: Record<string, unknown> | null`。列表接口 `GET /tasks/{id}/documents` 顺带返回,hover 无需额外请求。

**(d) 前端纯 CSS hover 弹窗(决策:纯 CSS)**:
- `import.tsx` `FileRow` 文件名 `<span>` 外包 `group relative` 容器,`group-hover` 时显示绝对定位卡片(文件名右下角,`--shadow-popover`,monochrome)。
- 卡片渲染画像核心字段:账户类型/持有人/机构/对账期间/收支规则/表头(header_attributes);`key_observations` 截断或省略。
- portrait 为空(未生成/未跑)时显示「画像待生成」占位。
- 注意表格容器 `overflow` 裁切:若弹窗被裁,调容器 overflow 或用 portal 兜底(优先调 overflow,不引依赖)。

**验收**:跑完一个任务,数据导入页文档列表 hover 文件名,右下角弹出画像卡片显示核心字段;未跑完的文档显示「画像待生成」。

## 验收前置条件(重要)

**LLM 兼容性不在本任务范围**(用户明确「不管」)。当前 modelscope `Qwen/Qwen3.5-35B-A3B` + pydantic-ai 的 `tool_choice:"required"` + `max_completion_tokens` 不兼容,导致分类/画像 LLM 调用返回空响应、全 excluded、画像生成失败。

因此:
- ② 日志:可独立验收(不依赖 LLM)。
- ③ 手动处理+并发:可独立验收流程(上传不自动跑、手动开始、批循环、并发限流),但**跑出来的分类结果仍会全 excluded**——这是 LLM 问题,不是本任务 bug。
- ④ 画像持久化+hover:portrait 列、持久化、API、hover 弹窗的**机制**可验收;但**画像内容会为空**(LLM 生成失败)——hover 显示「画像待生成」或空卡片是 LLM 问题,不是本任务 bug。

若用户在验收前修好 LLM(换兼容 endpoint 或修 agent_factory),则 ③④ 可看到完整真实效果。

## 实现顺序建议

1. ② 日志(最轻、独立、先做让后续调试看得见)
2. ① 窗栏(最轻、纯前端)
3. ④ 画像持久化(后端模型+迁移+API,前端 hover)
4. ③ 手动处理+并发(最重,放最后;依赖前几步的日志可见性来调试)

## 不做(范围外)

- LLM 兼容性修复(agent_factory 的 tool_choice/max_completion_tokens 适配)。
- 布局壳 PageHeader 接真实任务数据(任务名/客户/期间)——保留现有占位。
- 日志落盘文件 / LOG_LEVEL 配置项。
- 引入 radix popover/tooltip 依赖。
- 画像 hover 卡片的 portal 化(优先用 overflow 调整解决裁切)。
