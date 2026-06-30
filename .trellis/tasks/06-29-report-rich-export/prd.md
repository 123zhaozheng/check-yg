# 报告图文混排 PDF（pydantic-ai 单 agent + 结构化输出 + 5 图表工具）

> 现状痛点：每章一个 `agent.run` × 8 次 LLM 调用（`report_agent.py` 现范式）——章节间衔接断裂、
> 风格漂移，无图。
>
> 此次新建任务，对标 `yYorky/PydanticAI-Agent-Analyst`（单 agent + pydantic schema + matplotlib
> 图表）+ pydantic-ai 1.x 官方推荐的结构化输出路径（discriminated union）。一条 agentic run
> 写完整篇报告，目录由用户在 UI 预设并硬性注入 agent system prompt，~ 8000 字上下，导出
> 仅 PDF。删除 docx 路径（option B）。

## 现状（代码事实）

- 底座已稳（**复用，不重写**）：
  - `app/llm/analysis.py:259 ` `ReadAuditToolset`（5 只读工具：`get_task_summary` /
    `query_by_time` / `query_by_amount` / `query_by_counterparty` / `query_burst`，
    + `query_findings`）= **本次"关键词检索底座"**。
  - `app/llm/analysis.py:560` `get_dimension_agent` + `ReportDeps` dataclass 范式 =
    **本次"AI 分析底座"** 的 pydantic-ai 接线范本。
  - `_resolve_agent_params` + 阶段卡片 `STAGE_REPORT_GENERATION` 已接通，
    `app/llm/report_agent.py:149` `get_report_generation_model` 给复用一个口子。
  - `app/schemas/review.py` `Report` / `ReportChapter` 模型，PDF writer `multiBuild` 封面 +
    TOC 骨架（`export_service._write_report_pdf`）。
- 要替换/删除的：
  - `app/services/report_chapter_builder.py` 现"按章 dispatch 8 次 agent.run"（被替换）。
  - `app/services/export_service._write_report_docx` 全删（option B）。
  - `app/services/export_service._write_report_html` 不再走新管线（页面内已有前端
    `report.tsx` 看报告，html 导出保留旧路径兜底或一并退场—— PRD §非目标）。
- 待定：`matplotlib` 是否已在 venv 内 → 大概率是，需 `grep matplotlib` 确认；不缺则装
  （是否允许新增第 4 个绘图依赖见 §硬约束）。

## 一、核心范式（必须这样做）

### 1.1 单 agent + 结构化输出（替换 8 章分批）

```
Report Agent (pydantic-ai, 单 agent)
  instructions: 数据接地硬底线 + 报告写作策略 + 用户预设目录（硬性注入）
                + 何时该插哪种图表（决策规则）
  output_type:   ReportDocument              ← pydantic discriminated union
  toolsets:      [ReadAuditToolset (复用),
                 ChartToolset (新)]
```

`output_type` 定义（pydantic schema + discriminated union，pydantic-ai 官方推荐，
<https://pydantic.dev/docs/ai/core-concepts/output/>）：

```python
class HeadingBlock(BaseModel):
    kind: Literal["heading"] = "heading"
    level: int                       # 2 / 3（章标题系统加，不允许 1）
    text: str

class ParagraphBlock(BaseModel):
    kind: Literal["paragraph"] = "paragraph"
    text: str                        # 内联仅 **bold**（与现有约束子集一致）

class ListBlock(BaseModel):
    kind: Literal["list"] = "list"
    ordered: bool
    items: list[str]

class TableBlock(BaseModel):
    kind: Literal["table"] = "table"
    headers: list[str]
    rows: list[list[str]]

class ImageBlock(BaseModel):
    kind: Literal["image"] = "image"
    path: str                        # PNG 文件路径（ChartToolset 产出）
    caption: str | None = None

Block = Annotated[
    Union[HeadingBlock, ParagraphBlock, ListBlock, TableBlock, ImageBlock],
    Field(discriminator="kind"),
]

class Section(BaseModel):
    heading: str                     # 章标题
    blocks: list[Block]

class ReportDocument(BaseModel):
    task_summary: str                # 封面下方元信息用的简要（也用于开头概述）
    chapters: list[Section]
```

### 1.2 用户预设目录（硬性提示词注入）

- 前端 `report.tsx` 增加：可选章节列表（默认走内置 8 章，可增/可改每章标题），目标字数
  （默认 8000），底部「开始生成」按钮。
- 用户点击「开始生成」→ POST 时把目录 JSON（`["概述", "被审查对象", ...]`）传给后端 →
  服务端把它**拼进 agent 的 instructions** 里做硬性章节清单 + 字数预算。例如：

  ```
  ## 用户预设章节（硬性，必须严格按此顺序产出）
  1. 任务概述
  2. 数据范围分析
  3. 关键词审查命中
  4. 异常发现汇总
  5. 风险评估与建议

  ## 字数预算
  全文约 8000 字（每章按内容重要性分配 ±20%）。

  ## 图表插入策略
  - "数据范围分析"章必须含 1 张图（金额分布或 24h 热力图）。
  - "异常发现汇总"章可含 1 张图（对手方 Top-N）。
  - 其他章可选插图。
  ```

- 字数和章节数要在 instructions 里**作为硬约束**，渲染器并不强制（fail-open）—— agent
  出错字数过多 / 漏章时一致性问题尚可接受，MVP 不做运行时校验。

### 1.3 ChartToolset（5 个图，全员 matplotlib → PNG 路径）

注册为 `FunctionToolset[ReportDeps]`，tool 返回 PNG 路径 + 一句话 summary（工具
docstring 自动成工具描述）。所有工具带 limit（防爆 context）。

```
chart_amount_distribution()
  → 直方图，纵轴笔数 / 横轴金额区间，标 high_value_threshold 警戒线（默认 50000 元）。
cap 参数默认 50 条分桶。
返回：临时目录下 PNG path。

chart_counterparty_top()
  → Top-N 对手方（按 total_amount 降序），默认 N=10，标灰色深浅按金额大小。
可调参数：top_n（默认 10）、sort_by（amount|count，默认 amount）。

chart_time_pattern_24h()
  → 24h 交易密度图，x=小时 0-23，y=笔数；夜间时段 22-05 浅灰高亮。
返回：临时目录下 PNG path。

chart_daily_volume()
  → 按日聚合趋势线，x=日期，y=笔数；标 µ+2σ 警戒线。
返回：临时目录下 PNG path。

chart_channel_pie()
  → 渠道分布饼图（渠道 = 上传文件的多渠道：微信/支付宝/银行 X 等，见 flow_records.channel）。
返回：临时目录下 PNG path。
```

实现细节：
- matplotlib `plt.savefig(path, dpi=150, bbox_inches="tight")`（必须 `bbox_inches="tight"`
  否则渲染时被裁切，参考 <https://stackoverflow.com/questions/27871740>）。
- 中文 font fallback：`matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei",
  "Arial"]` + `axes.unicode_minus = False`，找不到仍能出图（用英文字符）。
- 临时目录：`backend/.tmp/charts/{task_id}/{timestamp}/`，保留到导出完成；定期清理任务可
  后续 P1 做。
- 工具 docstring 写明**何时调这道图**（含决策规则，如"金额异常堆时调用
  chart_amount_distribution"），让 agent 自己决定。

### 1.4 单 agent.run 编排

- 沿用 `_resolve_agent_params`（analysis.py 已有）+ `STAGE_REPORT_GENERATION` 阶段卡。
- `output_type=ReportDocument` → agent.run → `result.output` 是已校验的 schema 对象。
  （原文 markdown 路径全废。）
- agentic 多步工具循环：agent 可在一次 run 里多次调只读工具取数据 + 调图表工具画图 +
  最终一笔产出 `ReportDocument` schema。pydantic-ai 1.x 官方支持，conventions.md 已稳。
- 仅文字 / 仅图 / 文字+图都允许：agent 决策。
- 容错：
  - LLM 不可用 / 全部失败 → 整体失败，Report.status=failed + log。
  - LLM 部分产出报错（schema validation fail）→ 重试一次（一次内部预算，不无限循环）。
  - 第三次还是 fail → 回退"纯文本章节"模式：用现有 markdown 渲染器读 chapter.content
    模板输出（不动 agent）。**保留兜底为关键退化级**。

## 二、Renderer：ReportDocument → PDF

新增 `_write_rich_report_pdf(path, task, doc: ReportDocument)` 在 `export_service.py`。

- **不再走 markdown**：直接遍历 `doc.chapters[i].blocks`，按 kind 分派到 reportlab
  Flowable（复用 06-29 已 simhei 字体注册思路——本次先确认 venv 是否 matplotlib 已装，
  CN 字体仍通过 `pdfmetrics.registerFont(TTFont(...))`）。
- block → Flowable 映射：
  - `HeadingBlock`：ChapterHeading style（已黑体，level 2/3 小字）。
  - `ParagraphBlock`：`Paragraph(text)`，**bold** 用 `<b>` 标签（reportlab 支持，
    内联 `**bold**` 解析与现有方案统一）。
  - `ListBlock`：连续 `ListFlowable`，有序/无序按 ordered。
  - `TableBlock`：`Table`，表头加深底 + 白字（沿用现有 PRIMARY 主题），数据行斑马。
  - `ImageBlock`：`Image(str(path), width=PAGE_W * 0.85, height=auto)`（按页面宽 85%
    等比缩放，避"Flowable too large"错）；caption 用 `Paragraph(caption)` 图下注。
- 封面 / TOC / 页眉页脚 / 章节分页：复用 `_write_report_pdf` 的 helper
  (`_cover_meta_lines`, `_docx_cover_meta_lines` 等是 docx 写过的，需 pdf 版)。
  TOC 改为"用户预设章节清单" → 多页码条目，reportlab `TableOfContents` + `multiBuild`
  仍能 work（章标题 style 不变）。
- LLM 调用部分由 service 层组装 prompt + run + 落库（与现有 `build_all_chapters` 同级，
  新增 `build_rich_report`）。

## 三、删除 docx 路径（option B）

- `app/services/export_service._write_report_docx` 全删（不留函数）。
- `app/services/export_service._write_report_html` 不动（页面报告兜底用，前端
  `report.tsx` 已用来看）。
- `app/services/export_service.export_report` 不再有 `fmt="docx"` 分支，
  router `app/routers/exports.py` 调用方仍传 `fmt=pdf`。
- `tests/test_review_export.py` 里所有 docx 相关测试改写成：明确不生成、返回
  `NotImplementedError`（或 router 直接 400）。

## 四、新前端交互（不写前端，只定义接口）

- `report.tsx` 加 UI（前端 owner 工作）：
  - 可编辑章节列表（默认 8 章名单作为 base）。
  - 目标字数输入（默认 8000）。
  - 「开始生成」触发 → POST 时把 `chapter_titles: list[str]` + `target_chars: int` ==
    8000 一起带上。
- 新增 router：`POST /reports` / `GET /reports/{id}` 已存在；扩展请求体接受
  `chapter_titles` / `target_chars`，存到 `Report.config` 字段（已 `JSON` 类型）。

## 五、硬约束

- **不引重依赖**：matplotlib 唯一新增（如后端 venv 未装，需说明装包来源）。
- **不动 ReadAuditToolset**：完全复用 `analysis.py` 的 5 只读工具 + `query_findings`，不复制不重写。
- **不动分析 agent / 维度 agent**：本次只动报告层。
- **不动前端**：前端的章节列表 UI 是 owner 工作，PRD 只定义接口契约，便于 frontend agent
  接手。
- **不动 Report / ReportChapter 模型**：用现有 model，切忌为了新结构乱加列；新增字段用
  `Report.config: JSON`（已存在）或新加列（轻加）。
- **数据接地硬底线沿用 `report_agent.py:69-86`**：所有数字/对手方/日期必须来自工具
  返回，不得编造。落入新 agent instructions。
- **单 agent 输出结构 + 兜底** 不丢：纯文本章节兜底 = 兜底，agent 失败时 `Report.status`
  = `failed`，兜底失败时降级到模板（已在 `report_chapter_builder._build_*` 写的那些
  确定性模板）。

## 六、非目标（不做）

- ❌ docx 导出（已删 option B）。
- ❌ HTML 导出（`report.tsx` 前端已负责看）。
- ❌ 多 agent 协作 / 多文档编排（保持单 agent 编排）。
- ❌ 图表风格主题化（深度自定义色彩/字体交后续 P 任务）。
- ❌ 报告二次编辑 UI（导出后再让用户在 UI 改报告；不属本次）。
- ❌ 缓存图表 / 数据库存图（PNG 落地临时目录就够）。
- ❌ 真实 logo / 水印。

## 验收（DoD）

- [ ] 单 agent 跑通 `ReportDocument` 输出 + 调至少 1 次图表工具（含 PNG 落临时目录）。
- [ ] pydantic-ai `output_type` 用 discriminated union，schema 校验失败有日志。
- [ ] 用户目录（≥ 1 章改名 + 删减 + 增）注入 instructions，agent 输出严格匹配章节数与顺序。
- [ ] 5 个图表工具均注册并支持 agent 调用，每个有 docstring 描述 + 默认参数 + 单元测试。
- [ ] matplotlib 中文 fallback 写出非乱码 PNG（SimHei 找不到走默认 + 测试）。
- [ ] `_write_rich_report_pdf` 接受 `ReportDocument`，输出 PDF 含封面 + 用户目录 TOC + 章节 + 图表（含 caption）。
- [ ] docx 路径全删：`_write_report_docx` 函数删除；`fmt="docx"` 调用报
  `NotImplementedError` 或 router 返回 400；test_review_export 同步更新。
- [ ] 兜底：模拟 LLM 全部失败 → Report.status=failed；模拟 LLM 部分 schema 错误 →
  1 次重试 → 仍错 → 走纯 markdown 模板输出（不崩）。
- [ ] `tests/test_report_rich_export.py`（新文件）覆盖 schema 解析、5 个图表工具、
  renderer 路径、docx 路径已删。
- [ ] 全程**只 PDF**；路线无 docx/html 落地改动。
- [ ] 手测：跑一次端到端生成，导出 PDF 自己目视有封面 + TOC + 章节 + 至少 1 张图。

## 参考文件

- pydantic-ai output 官方文档（discriminated union 默认输出工具注册路径）:
  <https://pydantic.dev/docs/ai/core-concepts/output/>
- pydantic-ai tools advanced（工具返 Image / 文档路径）:
  <https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/>
- 同类开源参考 `yYorky/PydanticAI-Agent-Analyst`（单 agent + pydantic schema +
  matplotlib 落 PNG）: <https://github.com/yYorky/PydanticAI-Agent-Analyst>
- matplotlib → reportlab Platypus Image Flowable（含 "too large on page" 错与缩放方案）:
  <https://stackoverflow.com/questions/27871740>
- matplotlib → python-docx `add_picture(Inches(w), BytesIO)`:
  <https://stackoverflow.com/questions/53536286>
- HTML vs markdown for agent-to-human 报告（量化结论）:
  <https://beam.ai/agentic-insights/html-vs-markdown-which-format-actually-makes-ai-agents-more-useful>

## 项目内部

- `app/llm/analysis.py`（ReadAuditToolset / 维度 agent 范式 / deps / stage card）
- `app/llm/report_agent.py`（章节 agent + Stage card 接线 / 数据接地硬底线）
- `app/services/report_chapter_builder.py`（要被替换，但兜底模板可复用）
- `app/services/export_service.py`（PDF writer 骨架 / cover / TOC multiBuild）
- `app/services/report_markdown.py`（章节渲染器 + 兜底用）
- `app/models/report.py` / `report_chapter.py`（现有 schema，不动）
- `docs/research/pydantic-ai-conventions.md`（agent 接线规范）
