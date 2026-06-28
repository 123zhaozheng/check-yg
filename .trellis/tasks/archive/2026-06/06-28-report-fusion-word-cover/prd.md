# 报告 LLM 生成 + 富文本渲染 + Word/PDF 封面目录

> 报告内容由 **pydantic-ai agent 真正生成**（不再是模板/占位），模仿 AI 分析 agent 框架：
> **每章一个 agent.run**（像每个维度一个 run），数据接地（围绕 accepted findings / confirmed
> 关键词 / 余额校验 / 流水统计等**真实数据**写分析，禁止编造数字），输出**约束子集 markdown**。
> 导出加 **markdown 渲染器**（md→docx + md→pdf）让富文本正确排版（不显字面 `##`/`|`）。
> 生成改**异步后台 + 前端轮询**（8 章 8 次 LLM 调用 ≈ 1 分钟）。Word + PDF 统一**封面 + 目录**。

## 现状（代码事实）

- `report_chapter_builder.py`：`build_all_chapters()` 是**纯模板字符串**（无 LLM）；
  `get_report_generation_model(db)` + `STAGE_REPORT_GENERATION` 是**占位接线，从未接通**
  （注释明写"等后续任务接真实 agent.run"）。`_aggregate()` 已聚合 accepted findings +
  confirmed keyword（join）+ balance_check（Task 2 已加）。
- `export_service.py`：`_write_report_docx`/`_write_report_pdf` 把章节内容当**纯文本**
  （`add_paragraph` / `split("\n\n")+Paragraph`）——**markdown 的 `##`/`|`/`-` 字面显示**，
  这是「格式错乱」根因。封面 + 目录（Word 原生 TOC 域 / PDF multiBuild 两遍）已做。
- 生成流程同步：`generate_task_report`（reports.py:141）→ `build_all_chapters` → 存 8 章 → commit。
- 分析 agent 框架（要模仿）：`analysis.py` `get_dimension_agent`/`run_dimension` —— pydantic-ai
  `Agent(output_type, instructions, deps_type, toolsets)` + `get_agent` 单例 + `agent.run` +
  `_resolve_agent_params`（阶段卡片 → env 兜底）+ `get_stage_model`。

---

## 一、报告内容 = LLM agent 生成（每章一个 run，异步）

### 1.1 报告 agent（pydantic-ai，模仿分析 agent）
- 新建 `app/llm/report_agent.py`（或并入 report_chapter_builder）：
  - `ReportDeps` dataclass：`db, task_id` + 本章所需聚合数据（或 agent 只读工具取数——MVP 用**上下文喂数据**，不挂工具，更简）。
  - `get_report_agent(chapter_title, *, model)` → `get_agent(str, instructions, ..., deps_type=ReportDeps)`（output_type=str，章节正文 markdown；instructions 含本章写法 + 格式约束 + 数据接地硬底线）。
  - `run_chapter(deps, chapter_title, chapter_context_json, *, model) -> str`：`agent.run` → markdown 正文。
  - 复用 `_resolve_agent_params`（report_generation 阶段卡片 → env 兜底）+ `get_report_generation_model`（接通！）。
  - 守 `docs/research/pydantic-ai-conventions.md`（base_url /v1、deps_type、get_agent 单例、output_type）。

### 1.2 系统提示词（每章共用 + 章节专项）
- 共用：「你是银行/支付流水审查报告撰写专家。根据提供的**真实审查数据**撰写专业、丰满、
  格式规范的报告章节（markdown）。**只能使用提供的数据，严禁编造任何数字/对手方/日期**；
  空数据写「未发现」，不要凑数。语言专业客观。」
- **格式约束子集**（硬约束，渲染器只认这些）：
  - 章标题**不要**自己写（系统已加）——正文从 `##`（节）/`###`（小节）起。
  - 段落用空行分隔；要点用 `- ` 列表；强调用 `**加粗**`；表格用标准 markdown 表格（`| a | b |` + `|---|---|` 分隔行）。
  - **禁用**：HTML、代码块 ```、标题前缀 `# `（一级留给章标题）、嵌套列表、图片。
- 章节专项：每章 instructions 说明该章要写什么（概览=任务背景+审查范围总述；数据范围=笔数/金额/周期/渠道分布解读；完整性校验=余额校验结论解读；关键词审查=命中情况分析；发现汇总=accepted findings 归类综述；风险评估=high/medium 风险研判；结论=结论+建议）。

### 1.3 数据接地（每章 run 的上下文）
- `build_all_chapters`：先 `_aggregate(task)`（accepted findings / confirmed keyword / balance / 流水统计 / task 元信息）→ 按章切片成 JSON 上下文 → 每章 `run_chapter(title, context)`。
- agent 围绕真实数据写分析（数字/对手方/命中必须来自 context）。

### 1.4 异步生成 + 前端轮询（模仿分析任务异步模式）
- `generate_task_report`（POST）：立即建 `Report(status=generating)` + 8 个空 `ReportChapter`（content 占位）→ commit → 返 report（status=generating）→ **后台 job** 逐章 `run_chapter` 填 content + 增量 commit。
- 复用 analysis_service 的 background-job 模式（`asyncio.create_task` + 独立 session + 防重入）。
- **前端轮询**：report.tsx 拿到 status=generating → 轮询 GET report（每 ~1.5s）直到 status=generated（8 章 content 都填完）；逐章显示（已填的显内容，未填的显「生成中…」）。
- 单章重生成（`regenerate_chapter`，reports.py:270 已有）→ 同样调 `run_chapter` 单章。

### 1.5 兜底
- LLM 不可用 / agent 失败 → 该章回退现有**模板** `_build_*`（确定性内容，不崩）。
- 整体失败 → Report status=failed + log。

---

## 二、markdown 渲染器（md → docx + md → pdf，约束子集）

> 没有它，富 markdown 在 Word/PDF 里就是字面 `##`/`|`。新建轻量渲染器（手写，不引重依赖），
> 只认 §一.2 约束子集。

- 新建 `app/services/report_markdown.py`：
  - `parse_markdown_blocks(md) -> list[Block]`：行级解析 → 块（heading{level,text} / paragraph{text} / list_item{ordered,text} / table{headers,rows} / quote{text}）。inline 解析 `**bold**` → 加粗段。
  - `render_docx(doc, blocks)`：heading→`add_heading(level)`；paragraph→`add_paragraph`（`**` 拆 bold run）；list→`style='List Bullet'/'List Number'`；table→`add_table`+表头加粗。
  - `render_pdf(flowables, blocks, styles)`：heading→`Paragraph(style)`；paragraph→`Paragraph`（`<b>` 内联，先 escape）；list→`ListFlowable`；table→`Table`（表头灰底加粗）。
- `export_service._write_report_docx`/`_write_report_pdf`：章节正文从「纯文本 split」改为 `render_docx/pdf(parse_markdown_blocks(ch.content))`。章标题仍 Heading 1（`chapter_heading_style`，afterFlowable 抓 TOC 页码）。
- 单色硬底线：表格表头 `bg-ink-300`/灰底加粗；无彩色。

---

## 三、封面 + 目录（已做，保留）

Word + PDF 统一：整页封面（大标题「银行/支付流水审查报告」+ 副标题 task.title + 元信息块：
被审查人/周期/生成日期/任务编号 + 横线，无 logo）+ 目录（Word 原生 TOC 域 + 更新提示；
PDF TableOfContents + multiBuild 两遍真实页码）。封面→目录→正文分页。

---

## 四、数据来源
- accepted findings（`Finding status=accepted`，含 source=rule 维度 + source=balance_check）。
- confirmed keyword（`KeywordHit status=confirmed` join card/term/flow_record）。
- 流水统计（standard 笔数/金额/渠道/周期）+ task 元信息（employee/period）。
- 复用 `_aggregate`（已含上述）；不另起聚合。

## 五、验收标准
- [ ] `get_report_generation_model` **接通**真 agent；`build_all_chapters` 每章调 `run_chapter`
      产 LLM markdown（不再是模板字符串）。
- [ ] 系统提示词硬约束：只用提供数据、不编造数字；输出约束 markdown 子集（无 HTML/代码块/一级标题）。
- [ ] 生成**异步**：POST 立即返 generating，后台逐章填；前端轮询到 generated；单章 regenerate 也走 agent。
- [ ] LLM 不可用 → 回退模板，不崩；Report 失败态 + log。
- [ ] **markdown 渲染器**：md→docx + md→pdf 正确渲染标题/段落/列表/加粗/表格（不显字面符号）；
      现有模板章（关键词表格等）也正确渲染。
- [ ] 封面 + 目录（Word+PDF 统一）保留有效。
- [ ] 单测：markdown 块解析（各子集 + 边界）、docx/pdf render smoke、run_chapter mock（mock agent
      返 markdown）、异步生成 job（逐章填 + 失败兜底）、数据接地（context 含真实聚合）。

## 六、风险
| 风险 | 缓解 |
|---|---|
| LLM 编造数字/对手方 | 系统提示词硬约束 + 数据全在 context + 输出约束子集 |
| markdown 格式乱（LLM 不守子集） | 约束子集 + 渲染器只认子集（不认的当段落）+ 提示词强约束 |
| 8 章 8 次 LLM 慢/超时 | 异步后台 + 前端轮询（不阻塞 HTTP）+ 防重入 |
| 单章 agent 失败 | try/except 该章回退模板，不阻塞其他章 |
| markdown 渲染器边界（畸形表格/列表） | 解析器容错（认不全的当段落）+ 单测覆盖 |
| 已有 ReportAnnotation order_index | 章节按 order_index，agent 填 content 不改 order_index |

## 七、实现分两步（建议）
1. **Phase 1 — markdown 渲染器**（`report_markdown.py` + 接入 export）：独立可验，先把现有
   模板章在 Word/PDF 里渲染对（不再字面符号）。
2. **Phase 2 — LLM 报告 agent + 异步**：`report_agent.py` + 接通 `get_report_generation_model`
   + `build_all_chapters` 改 agent + 异步 job + 前端轮询 + 兜底。
