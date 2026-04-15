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
    "experience_summary": [
        "专家通常先看任务规模，再看命中分布，再回到证据明细。",
        "证据型问题优先读取最终审查流水。",
        "异常型问题优先关注夜间交易、重复金额、集中交易和重点对手。",
        "如用户提出新重要维度，建议追问是否沉淀为标准能力。",
    ],
    "historical_focus_dimensions": [
        {"dimension": name, "count": count}
        for name, count in dimension_counter.most_common(10)
    ],
}

target = get_output_dir() / "expert_experience_summary.json"
write_json(target, payload)
print(target)
