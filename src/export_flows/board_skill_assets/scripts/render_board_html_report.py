# -*- coding: utf-8 -*-
import json

from common import OUT_ROOT, ROOT

summary = json.loads((OUT_ROOT / "board_summary_data.json").read_text(encoding="utf-8"))
template = (ROOT / "assets" / "board_report_template.html").read_text(encoding="utf-8")

html = template
html = html.replace("{{REPORT_TITLE}}", summary.get("report_title", "审查看板汇总报告"))
html = html.replace("{{REPORT_SUBTITLE}}", summary.get("report_subtitle", ""))
html = html.replace("{{TASK_COUNT}}", str(summary.get("task_count", 0)))
html = html.replace("{{TOTAL_MATCHES}}", str(summary.get("total_matches", 0)))
html = html.replace("{{MATCHED_CUSTOMERS}}", str(summary.get("matched_customers", 0)))
html = html.replace("{{TOTAL_AMOUNT}}", str(summary.get("total_amount", "")))
html = html.replace("{{TASK_SERIES_JSON}}", json.dumps(summary.get("task_series", {}), ensure_ascii=False))

target = OUT_ROOT / "看板概览报告.html"
target.write_text(html, encoding="utf-8")
print(target)
