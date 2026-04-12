# -*- coding: utf-8 -*-
import argparse
import json

from common import ROOT, get_task_output_dir

parser = argparse.ArgumentParser()
parser.add_argument("--task-id", required=True)
args = parser.parse_args()

task_out = get_task_output_dir(args.task_id)
report_data = json.loads((task_out / "report_data.json").read_text(encoding="utf-8"))
narrative_path = task_out / "narrative.json"
narrative = json.loads(narrative_path.read_text(encoding="utf-8")) if narrative_path.exists() else {
    "title": f"{report_data.get('task_title', '')} 审查分析报告",
    "executive_summary": [],
    "sections": [],
    "conclusion": "",
}
template = (ROOT / "assets" / "task_report_template.html").read_text(encoding="utf-8")

narrative_html = []
for item in narrative.get("executive_summary", []):
    narrative_html.append(f"<p>{item}</p>")
for section in narrative.get("sections", []):
    narrative_html.append(f"<h3>{section.get('title', '')}</h3>")
    for text in section.get("content", []):
        narrative_html.append(f"<p>{text}</p>")
if narrative.get("conclusion"):
    narrative_html.append("<h3>结论与建议</h3>")
    narrative_html.append(f"<p>{narrative.get('conclusion', '')}</p>")

counterparty_rows = []
for item in report_data.get("top_counterparties", []):
    counterparty_rows.append(
        "<tr>"
        f"<td>{item.get('counterparty_name', '')}</td>"
        f"<td>{item.get('transaction_count', 0)}</td>"
        f"<td>{item.get('total_amount', '')}</td>"
        f"<td>{item.get('time_range', {}).get('start', '')} 至 {item.get('time_range', {}).get('end', '')}</td>"
        "</tr>"
    )

evidence_rows = []
for item in report_data.get("evidence_rows", []):
    evidence_rows.append(
        "<tr>"
        f"<td>{item.get('流水行号', '')}</td>"
        f"<td>{item.get('匹配用户', '')}</td>"
        f"<td>{item.get('交易时间', '')}</td>"
        f"<td>{item.get('交易对手名', '')}</td>"
        f"<td>{item.get('金额', '')}</td>"
        f"<td>{item.get('摘要', '')}</td>"
        "</tr>"
    )

match_type_series = [{"name": k, "value": v} for k, v in (report_data.get("match_type_distribution", {}) or {}).items()]
counterparty_series = {
    "labels": [item.get("counterparty_name", "") for item in report_data.get("top_counterparties", [])[:8]],
    "counts": [item.get("transaction_count", 0) for item in report_data.get("top_counterparties", [])[:8]],
}
customer_series = {
    "labels": [item.get("customer_name", "") for item in report_data.get("top_customers", [])[:8]],
    "counts": [item.get("match_count", 0) for item in report_data.get("top_customers", [])[:8]],
}
night_series = [
    {"name": "夜间交易", "value": report_data.get("night_transactions", {}).get("count", 0)},
    {"name": "非夜间交易", "value": max(report_data.get("flow_count", 0) - report_data.get("night_transactions", {}).get("count", 0), 0)},
]

html = template
html = html.replace("{{REPORT_TITLE}}", narrative.get("title", "审查分析报告"))
html = html.replace("{{TASK_TITLE}}", str(report_data.get("task_title", "")))
html = html.replace("{{TASK_ID}}", str(report_data.get("task_id", "")))
html = html.replace("{{REVIEW_TIME}}", str(report_data.get("review_time", "")))
html = html.replace("{{FLOW_COUNT}}", str(report_data.get("flow_count", 0)))
html = html.replace("{{MATCHED_FLOW_COUNT}}", str(report_data.get("matched_flow_count", 0)))
html = html.replace("{{MATCHED_CUSTOMER_COUNT}}", str(report_data.get("matched_customer_count", 0)))
html = html.replace("{{TOTAL_AMOUNT}}", str(report_data.get("total_amount", "")))
html = html.replace("{{EXACT_MATCH_COUNT}}", str(report_data.get("exact_match_count", 0)))
html = html.replace("{{DESENSITIZED_MATCH_COUNT}}", str(report_data.get("desensitized_match_count", 0)))
html = html.replace("{{FUZZY_MATCH_COUNT}}", str(report_data.get("fuzzy_match_count", 0)))
html = html.replace("{{NIGHT_COUNT}}", str(report_data.get("night_transactions", {}).get("count", 0)))
html = html.replace("{{SHORT_INTERVAL_COUNT}}", str(len(report_data.get("short_interval_cases", []))))
html = html.replace("{{SAME_AMOUNT_COUNT}}", str(len(report_data.get("same_amount_cases", []))))
html = html.replace("{{NARRATIVE_HTML}}", "".join(narrative_html))
html = html.replace("{{COUNTERPARTY_ROWS}}", "\n".join(counterparty_rows))
html = html.replace("{{EVIDENCE_ROWS}}", "\n".join(evidence_rows))
html = html.replace("{{MONTHLY_SERIES_JSON}}", json.dumps(report_data.get("monthly_amount_series", {}), ensure_ascii=False))
html = html.replace("{{MATCH_TYPE_SERIES_JSON}}", json.dumps(match_type_series, ensure_ascii=False))
html = html.replace("{{COUNTERPARTY_SERIES_JSON}}", json.dumps(counterparty_series, ensure_ascii=False))
html = html.replace("{{CUSTOMER_SERIES_JSON}}", json.dumps(customer_series, ensure_ascii=False))
html = html.replace("{{NIGHT_SERIES_JSON}}", json.dumps(night_series, ensure_ascii=False))

target = task_out / f"{args.task_id}_审查分析报告.html"
target.write_text(html, encoding="utf-8")
print(target)
