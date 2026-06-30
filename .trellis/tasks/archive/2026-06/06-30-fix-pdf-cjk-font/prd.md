# 修复 PDF 导出中文豆腐块

## 背景 / 根因

报告导出 PDF 后，所有中文显示成黑色方块（豆腐块）。

**根因**：`backend/app/services/export_service.py::_write_report_pdf` 给所有 `ParagraphStyle` 写死 `fontName="Helvetica"` / `"Helvetica-Bold"`（共 11 处：L361/370/381/391/402/412/421/432/480/490/501），并把这套全 Helvetica 的 `md_styles` 传给 `report_markdown.render_pdf`，**完全绕过** `report_markdown.py` 里已有的 CID 宋体兜底逻辑。Helvetica 仅含拉丁字形 → 中文全变豆腐块。

**已实测**：`UnicodeCIDFont("STSong-Light")` 在本机注册成功。`report_markdown.py` 默认样式已用 CID（body/quote），但 export_service 永远传自己的样式，所以没生效。

**覆盖面**：表格单元格也是 `Paragraph(..., styles["body"])`（report_markdown.py L581/585），所以整个 PDF 所有文字（封面/目录/章节标题/正文/表格/批注/markdown h2/h3/引用）都受 export_service 那批样式管辖。改一处文件即全覆盖。

## 非目标

- 不改 HTML 导出（`_write_report_html` 用 CSS `font-family:'SimSun'/'SimHei'`，浏览器解析正常）。
- 不改 `report_markdown.py` 默认样式（latent，当前无调用方走 styles=None，本次不动；surgical）。
- 不引入 TTF 字体文件 / 不依赖 Windows 系统字体（Docker 部署要跨平台）。
- 不做「标题加粗」（STSong-Light 无 bold 变体，靠字号层级区分；要粗体黑体是 follow-up）。

## 方案

文件：`backend/app/services/export_service.py`，只改 `_write_report_pdf`（L307-527）。

1. 在函数顶部 reportlab imports 之后，注册内置 CID 宋体：
   ```python
   from reportlab.pdfbase import pdfmetrics
   from reportlab.pdfbase.cidfonts import UnicodeCIDFont
   CN_FONT = "STSong-Light"
   if CN_FONT not in pdfmetrics.getRegisteredFontNames():
       pdfmetrics.registerFont(UnicodeCIDFont(CN_FONT))
   ```
2. 把 11 处 `fontName="Helvetica"` 和 `fontName="Helvetica-Bold"` 全部替换为 `fontName=CN_FONT`（或字面量 `"STSong-Light"`，二选一，用 CN_FONT 常量更清晰）。

涉及样式：cover_title_style / cover_sub_style / cover_meta_style / toc_title_style / chapter_heading_style / body_style / ann_style / TOC levelStyles[0] / md_styles 的 h2·h3·quote。

## 验收标准

1. 生成一份报告 PDF，封面/目录/章节标题/正文/表格/批注的中文均正常显示，无豆腐块。
2. PDF 内嵌字体包含 STSong-Light（不再是纯 Helvetica/Helvetica-Bold）。
3. HTML 导出不受影响（回归，本就不报错）。
4. 现有导出相关测试不回归。

## 验证方式

写个临时脚本或调导出端点生成一份含中文的 PDF；可解析 PDF 的 `/BaseFont` 确认含 STSong-Light；或直接打开 PDF 目测。sub-agent 自行选择最简方式验证并报告结果。

## 风险

- STSong-Light 是宋体单字重，标题不加粗（靠字号层级）——已知权衡，可接受。
- reportlab CID 字体 CMap 随包发布，Docker/Linux 环境同样可用，无平台依赖。
