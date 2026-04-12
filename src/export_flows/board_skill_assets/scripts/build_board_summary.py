# -*- coding: utf-8 -*-
from collections import Counter

from common import OUT_ROOT, list_tasks, load_summary, load_task_profile, write_json

summary = load_summary()
task_rows = []
match_type_counter = Counter()

for task in list_tasks():
    profile = load_task_profile(task["task_id"])
    task_rows.append({
        "task_id": task.get("task_id", ""),
        "task_title": task.get("task_title", ""),
        "total_matches": int(profile.get("total_matches", 0) or 0),
        "matched_customers": int(profile.get("matched_customers", 0) or 0),
        "review_amount": profile.get("review_amount", ""),
    })
    for key, value in (profile.get("match_type_distribution", {}) or {}).items():
        match_type_counter[key] += int(value or 0)

payload = {
    "report_title": f"审查看板汇总报告（{summary.get('task_count', 0)}个任务）",
    "report_subtitle": "展示已导出任务的整体审查规模和命中分布。",
    "task_count": int(summary.get("task_count", 0) or 0),
    "total_matches": int(summary.get("total_matches", 0) or 0),
    "matched_customers": int(summary.get("total_matched_customers", 0) or 0),
    "total_amount": summary.get("total_review_amount", ""),
    "task_series": {
        "labels": [row["task_title"] or row["task_id"] for row in task_rows],
        "matches": [row["total_matches"] for row in task_rows],
    },
    "task_rows": task_rows,
}

write_json(OUT_ROOT / "board_summary_data.json", payload)
print(OUT_ROOT / "board_summary_data.json")
