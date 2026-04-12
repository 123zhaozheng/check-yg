# -*- coding: utf-8 -*-
import argparse

from common import (
    build_match_type_counts,
    build_monthly_series,
    build_night_info,
    build_same_amount_cases,
    build_short_interval_cases,
    build_top_counterparties,
    build_top_customers,
    format_amount,
    get_field,
    get_task_output_dir,
    load_final_rows,
    load_task_profile,
    load_task_review,
    matched_rows,
    parse_amount,
    write_json,
)

parser = argparse.ArgumentParser()
parser.add_argument("--task-id", required=True)
args = parser.parse_args()

profile = load_task_profile(args.task_id)
review = load_task_review(args.task_id)
rows = load_final_rows(args.task_id)
hits = matched_rows(rows)
match_type_counts = build_match_type_counts(review)
night_info = build_night_info(rows)
payload = {
    "task_id": args.task_id,
    "task_title": profile.get("task_title", ""),
    "review_time": profile.get("review_time", ""),
    "review_id": profile.get("review_id", ""),
    "flow_count": len(rows),
    "matched_flow_count": len(hits),
    "total_matches": int(review.get("total_matches", 0) or 0),
    "customer_count": int(review.get("total_customers", 0) or 0),
    "matched_customer_count": int(review.get("matched_customers", 0) or 0),
    "total_amount": format_amount(sum(parse_amount(get_field(row, "金额")) for row in rows)),
    "matched_amount": format_amount(sum(parse_amount(get_field(row, "金额")) for row in hits)),
    "exact_match_count": int(match_type_counts.get("精确匹配", 0) or 0),
    "desensitized_match_count": int(match_type_counts.get("脱敏匹配", 0) or 0),
    "fuzzy_match_count": int(match_type_counts.get("模糊匹配", 0) or 0),
    "match_type_distribution": match_type_counts,
    "monthly_amount_series": build_monthly_series(rows),
    "top_counterparties": build_top_counterparties(rows),
    "top_customers": build_top_customers(rows),
    "night_transactions": night_info,
    "same_amount_cases": build_same_amount_cases(rows),
    "short_interval_cases": build_short_interval_cases(rows),
    "evidence_rows": [{
        "流水行号": row.get("流水行号", ""),
        "匹配用户": get_field(row, "匹配用户"),
        "交易时间": get_field(row, "交易时间"),
        "交易对手名": get_field(row, "交易对手名"),
        "金额": get_field(row, "金额"),
        "摘要": get_field(row, "摘要"),
    } for row in hits[:20]],
    "narrative_input": {
        "task_title": profile.get("task_title", ""),
        "flow_count": len(rows),
        "matched_flow_count": len(hits),
        "total_matches": int(review.get("total_matches", 0) or 0),
        "matched_customer_count": int(review.get("matched_customers", 0) or 0),
        "exact_match_count": int(match_type_counts.get("精确匹配", 0) or 0),
        "desensitized_match_count": int(match_type_counts.get("脱敏匹配", 0) or 0),
        "fuzzy_match_count": int(match_type_counts.get("模糊匹配", 0) or 0),
        "total_amount": format_amount(sum(parse_amount(get_field(row, "金额")) for row in rows)),
        "night_transaction_count": night_info["count"],
        "night_transaction_amount": night_info["amount"],
        "top_counterparties": build_top_counterparties(rows)[:5],
        "top_customers": build_top_customers(rows)[:5],
        "same_amount_cases": build_same_amount_cases(rows)[:5],
        "short_interval_cases": build_short_interval_cases(rows)[:5],
        "monthly_amount_series": build_monthly_series(rows),
    },
}

target = get_task_output_dir(args.task_id) / "report_data.json"
write_json(target, payload)
print(target)
