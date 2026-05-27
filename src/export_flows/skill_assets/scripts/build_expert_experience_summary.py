# -*- coding: utf-8 -*-
from collections import Counter

from common import get_output_dir, load_history_index, load_task_profile, write_json

profile = load_task_profile()
history = load_history_index()
match_type_counter = Counter()
dimension_counter = Counter()
for item in history.get("history_reviews", []):
    for dim in item.get("notable_dimensions", []) or []:
        dimension_counter[str(dim)] += 1

payload = {
    "task_id": profile.get("task_id", ""),
    "task_title": profile.get("task_title", ""),
    "history_review_count": history.get("history_review_count", 0),
    "review_process_summary": [
        "完整审查先确认资产，再读取任务画像和审查结果。",
        "证据型问题优先读取最终审查流水。",
        "默认审查维度以 references/审查维度清单.json 为准。",
        "如用户提出新重要维度，先判断是否补充已有维度；确属新维度再新增清单项和算子。",
    ],
    "historical_focus_dimensions": [
        {"dimension": name, "count": count}
        for name, count in dimension_counter.most_common(10)
    ],
}

target = get_output_dir() / "expert_experience_summary.json"
write_json(target, payload)
print(target)
