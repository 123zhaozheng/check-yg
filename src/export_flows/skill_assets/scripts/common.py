# -*- coding: utf-8 -*-
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
CURRENT_ROOT = ROOT / "current_task"
HISTORY_ROOT = ROOT / "历史审查目录"
REF_ROOT = ROOT / "references"
EXPERT_ROOT = ROOT / "expert_workflow"
OUT_ROOT = ROOT / "output"


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def parse_amount(value: object) -> float:
    text = normalize_text(value)
    if not text:
        return 0.0
    clean = (
        text.replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("元", "")
        .replace("+", "")
        .replace("-", "")
    )
    try:
        return abs(float(clean))
    except (ValueError, TypeError):
        return 0.0


def format_amount(value: float) -> str:
    return f"¥{value:,.2f}"


def parse_datetime(value: object) -> Optional[datetime]:
    text = normalize_text(value)
    if not text:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def load_assets_manifest() -> Dict:
    return load_json(REF_ROOT / "assets_manifest.json")


def load_workflow_context() -> Dict:
    return load_json(CURRENT_ROOT / "workflow_context.json")


def load_task_profile() -> Dict:
    return load_json(CURRENT_ROOT / "任务画像.json")


def load_task_review() -> Dict:
    return load_json(CURRENT_ROOT / "审查结果.json")


def load_history_index() -> Dict:
    return load_json(HISTORY_ROOT / "history_index.json")


def load_dimension_catalog() -> Dict:
    return load_json(REF_ROOT / "审查维度清单.json")


def get_field(row: Dict, field: str) -> str:
    aliases = {
        "交易对手名": ["交易对手名", "对手名"],
        "匹配用户": ["匹配用户"],
        "交易时间": ["交易时间"],
        "金额": ["金额"],
        "摘要": ["摘要"],
        "匹配度": ["匹配度"],
    }
    for key in aliases.get(field, [field]):
        value = row.get(key, "")
        if value not in ("", None):
            return normalize_text(value)
    return ""


def _load_excel_rows(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = next(rows_iter, None)
        if not headers:
            return []
        header_names = [normalize_text(item) for item in headers]
        rows = []
        for row_index, row in enumerate(rows_iter, start=2):
            item = {"流水行号": row_index}
            for idx, header in enumerate(header_names):
                if not header:
                    continue
                value = row[idx] if idx < len(row) else ""
                item[header] = "" if value is None else str(value).strip()
            if any(normalize_text(v) for k, v in item.items() if k != "流水行号"):
                rows.append(item)
        return rows
    finally:
        wb.close()


def load_final_rows() -> List[Dict]:
    rows = _load_excel_rows(CURRENT_ROOT / "最终审查流水.xlsx")
    if rows:
        return rows
    return _load_excel_rows(CURRENT_ROOT / "标准化流水.xlsx")


def matched_rows(rows: List[Dict]) -> List[Dict]:
    return [row for row in rows if get_field(row, "匹配用户")]


def build_match_type_counts(review: Dict) -> Dict:
    counter = Counter()
    for match in review.get("matches", []) or []:
        match_type = normalize_text(match.get("match_type", ""))
        if match_type:
            counter[match_type] += 1
    return dict(counter)


def build_monthly_series(rows: List[Dict]) -> Dict:
    totals = defaultdict(float)
    for row in rows:
        dt = parse_datetime(get_field(row, "交易时间"))
        if not dt:
            continue
        totals[dt.strftime("%Y-%m")] += parse_amount(get_field(row, "金额"))
    labels = sorted(totals.keys())
    return {"labels": labels, "amounts": [round(totals[item], 2) for item in labels]}


def build_top_counterparties(rows: List[Dict], top_n: int = 10) -> List[Dict]:
    grouped = defaultdict(lambda: {"count": 0, "amount": 0.0, "times": []})
    for row in rows:
        name = get_field(row, "交易对手名")
        if not name:
            continue
        grouped[name]["count"] += 1
        grouped[name]["amount"] += parse_amount(get_field(row, "金额"))
        dt = parse_datetime(get_field(row, "交易时间"))
        if dt:
            grouped[name]["times"].append(dt)
    items = []
    for name, data in grouped.items():
        valid_times = sorted(data["times"])
        items.append({
            "counterparty_name": name,
            "transaction_count": data["count"],
            "total_amount": format_amount(data["amount"]),
            "time_range": {
                "start": valid_times[0].strftime("%Y-%m-%d %H:%M:%S") if valid_times else "",
                "end": valid_times[-1].strftime("%Y-%m-%d %H:%M:%S") if valid_times else "",
            },
        })
    items.sort(key=lambda x: x["transaction_count"], reverse=True)
    return items[:top_n]


def build_top_customers(rows: List[Dict], top_n: int = 10) -> List[Dict]:
    grouped = defaultdict(lambda: {"count": 0, "amount": 0.0})
    for row in matched_rows(rows):
        customer = get_field(row, "匹配用户")
        if not customer:
            continue
        grouped[customer]["count"] += 1
        grouped[customer]["amount"] += parse_amount(get_field(row, "金额"))
    items = [{
        "customer_name": name,
        "match_count": data["count"],
        "match_amount": format_amount(data["amount"]),
    } for name, data in grouped.items()]
    items.sort(key=lambda x: x["match_count"], reverse=True)
    return items[:top_n]


def build_night_info(rows: List[Dict]) -> Dict:
    items = []
    for row in rows:
        dt = parse_datetime(get_field(row, "交易时间"))
        if dt and (dt.hour >= 22 or dt.hour < 6):
            items.append(row)
    amount = sum(parse_amount(get_field(row, "金额")) for row in items)
    return {
        "count": len(items),
        "amount": format_amount(amount),
        "rows": [{
            "流水行号": row.get("流水行号", ""),
            "交易时间": get_field(row, "交易时间"),
            "交易对手名": get_field(row, "交易对手名"),
            "金额": get_field(row, "金额"),
            "摘要": get_field(row, "摘要"),
        } for row in items[:20]],
    }


def build_same_amount_cases(rows: List[Dict]) -> List[Dict]:
    grouped = defaultdict(list)
    for row in rows:
        dt = parse_datetime(get_field(row, "交易时间"))
        name = get_field(row, "交易对手名")
        amount = parse_amount(get_field(row, "金额"))
        if not dt or not name or amount <= 0:
            continue
        grouped[(name, dt.strftime("%Y-%m-%d"), round(amount, 2))].append(row)
    cases = []
    for (name, tx_date, amount), items in grouped.items():
        if len(items) >= 2:
            cases.append({
                "counterparty_name": name,
                "transaction_date": tx_date,
                "same_amount": format_amount(amount),
                "transaction_count": len(items),
            })
    cases.sort(key=lambda x: x["transaction_count"], reverse=True)
    return cases[:20]


def build_short_interval_cases(rows: List[Dict]) -> List[Dict]:
    grouped = defaultdict(list)
    for row in rows:
        dt = parse_datetime(get_field(row, "交易时间"))
        name = get_field(row, "交易对手名")
        if dt and name:
            grouped[name].append((dt, row))
    cases = []
    for name, items in grouped.items():
        items.sort(key=lambda x: x[0])
        cluster = []
        for dt, row in items:
            if not cluster:
                cluster = [(dt, row)]
                continue
            if dt - cluster[-1][0] <= timedelta(minutes=30):
                cluster.append((dt, row))
            else:
                if len(cluster) >= 2:
                    cases.append({"counterparty_name": name, "transaction_count": len(cluster)})
                cluster = [(dt, row)]
        if len(cluster) >= 2:
            cases.append({"counterparty_name": name, "transaction_count": len(cluster)})
    cases.sort(key=lambda x: x["transaction_count"], reverse=True)
    return cases[:20]


def build_evidence_rows(rows: List[Dict], limit: int = 20) -> List[Dict]:
    return [{
        "流水行号": row.get("流水行号", ""),
        "匹配用户": get_field(row, "匹配用户"),
        "交易时间": get_field(row, "交易时间"),
        "交易对手名": get_field(row, "交易对手名"),
        "金额": get_field(row, "金额"),
        "摘要": get_field(row, "摘要"),
    } for row in matched_rows(rows)[:limit]]


def build_historical_similarity() -> Dict:
    history = load_history_index()
    dimension_counter = Counter()
    for item in history.get("history_reviews", []) or []:
        for dimension in item.get("notable_dimensions", []) or []:
            name = normalize_text(dimension)
            if name:
                dimension_counter[name] += 1
    return {
        "history_review_count": history.get("history_review_count", 0),
        "historical_focus_dimensions": [
            {"dimension": name, "count": count}
            for name, count in dimension_counter.most_common(10)
        ],
    }


def build_dimension_results(include_disabled: bool = False) -> Dict:
    profile = load_task_profile()
    review = load_task_review()
    rows = load_final_rows()
    hits = matched_rows(rows)
    match_type_counts = build_match_type_counts(review)
    catalog = load_dimension_catalog()

    operator_results = {
        "basic_scope_hits": {
            "task_id": profile.get("task_id", ""),
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
        },
        "match_type_distribution": {
            "match_type_distribution": match_type_counts,
            "exact_match_count": int(match_type_counts.get("精确匹配", 0) or 0),
            "desensitized_match_count": int(match_type_counts.get("脱敏匹配", 0) or 0),
            "fuzzy_match_count": int(match_type_counts.get("模糊匹配", 0) or 0),
        },
        "matched_customer_concentration": build_top_customers(rows),
        "counterparty_concentration": build_top_counterparties(rows),
        "night_transactions": build_night_info(rows),
        "monthly_trend": build_monthly_series(rows),
        "same_amount_repeat": build_same_amount_cases(rows),
        "short_interval_cluster": build_short_interval_cases(rows),
        "evidence_rows": build_evidence_rows(rows),
        "historical_similarity": build_historical_similarity,
    }

    dimensions = []
    for dimension in catalog.get("dimensions", []) or []:
        if not include_disabled and not dimension.get("default_enabled", False):
            continue
        operator_name = normalize_text(dimension.get("operator_name", ""))
        result = operator_results.get(operator_name, {})
        if callable(result):
            result = result()
        dimensions.append({
            "id": dimension.get("id", ""),
            "name": dimension.get("name", ""),
            "operator_script": dimension.get("operator_script", ""),
            "operator_name": operator_name,
            "output_key": dimension.get("output_key", operator_name),
            "result": result,
        })

    return {
        "dimension_catalog_file": "references/审查维度清单.json",
        "dimensions": dimensions,
    }


def get_output_dir() -> Path:
    path = OUT_ROOT / "review_outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path
