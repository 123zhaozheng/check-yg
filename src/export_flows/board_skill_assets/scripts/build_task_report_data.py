# -*- coding: utf-8 -*-
import argparse

from common import (
    build_dimension_results,
    get_task_output_dir,
    load_task_profile,
    write_json,
)

parser = argparse.ArgumentParser()
parser.add_argument("--task-id", required=True)
args = parser.parse_args()

profile = load_task_profile(args.task_id)
dimension_results = build_dimension_results(args.task_id)
dimension_map = {
    item.get("output_key") or item.get("operator_name"): item.get("result")
    for item in dimension_results.get("dimensions", [])
}
basic = dimension_map.get("basic_scope_hits", {})
match_types = dimension_map.get("match_type_distribution", {})
night_info = dimension_map.get("night_transactions", {})
payload = {
    "task_id": args.task_id,
    "task_title": profile.get("task_title", ""),
    "review_time": profile.get("review_time", ""),
    "review_id": profile.get("review_id", ""),
    "flow_count": basic.get("flow_count", 0),
    "matched_flow_count": basic.get("matched_flow_count", 0),
    "total_matches": basic.get("total_matches", 0),
    "customer_count": basic.get("customer_count", 0),
    "matched_customer_count": basic.get("matched_customer_count", 0),
    "total_amount": basic.get("total_amount", ""),
    "matched_amount": basic.get("matched_amount", ""),
    "exact_match_count": match_types.get("exact_match_count", 0),
    "desensitized_match_count": match_types.get("desensitized_match_count", 0),
    "fuzzy_match_count": match_types.get("fuzzy_match_count", 0),
    "match_type_distribution": match_types.get("match_type_distribution", {}),
    "monthly_amount_series": dimension_map.get("monthly_amount_series", {}),
    "top_counterparties": dimension_map.get("top_counterparties", []),
    "top_customers": dimension_map.get("top_customers", []),
    "night_transactions": night_info,
    "same_amount_cases": dimension_map.get("same_amount_cases", []),
    "short_interval_cases": dimension_map.get("short_interval_cases", []),
    "evidence_rows": dimension_map.get("evidence_rows", []),
    "dimension_results": dimension_results,
    "narrative_input": {
        "task_title": profile.get("task_title", ""),
        "flow_count": basic.get("flow_count", 0),
        "matched_flow_count": basic.get("matched_flow_count", 0),
        "total_matches": basic.get("total_matches", 0),
        "matched_customer_count": basic.get("matched_customer_count", 0),
        "exact_match_count": match_types.get("exact_match_count", 0),
        "desensitized_match_count": match_types.get("desensitized_match_count", 0),
        "fuzzy_match_count": match_types.get("fuzzy_match_count", 0),
        "total_amount": basic.get("total_amount", ""),
        "night_transaction_count": night_info.get("count", 0),
        "night_transaction_amount": night_info.get("amount", ""),
        "top_counterparties": dimension_map.get("top_counterparties", [])[:5],
        "top_customers": dimension_map.get("top_customers", [])[:5],
        "same_amount_cases": dimension_map.get("same_amount_cases", [])[:5],
        "short_interval_cases": dimension_map.get("short_interval_cases", [])[:5],
        "monthly_amount_series": dimension_map.get("monthly_amount_series", {}),
    },
}

target = get_task_output_dir(args.task_id) / "report_data.json"
write_json(target, payload)
print(target)
