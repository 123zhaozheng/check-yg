# -*- coding: utf-8 -*-
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
    get_output_dir,
    load_assets_manifest,
    load_final_rows,
    load_task_profile,
    load_task_review,
    matched_rows,
    parse_amount,
    write_json,
)

profile = load_task_profile()
review = load_task_review()
rows = load_final_rows()
hits = matched_rows(rows)
match_type_counts = build_match_type_counts(review)
night_info = build_night_info(rows)
payload = {
    "task_id": profile.get("task_id", ""),
    "task_title": profile.get("task_title", ""),
    "review_time": profile.get("review_time", ""),
    "review_id": profile.get("review_id", ""),
    "assets": load_assets_manifest().get("current_task", {}),
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
}

target = get_output_dir() / "review_context.json"
write_json(target, payload)
print(target)
