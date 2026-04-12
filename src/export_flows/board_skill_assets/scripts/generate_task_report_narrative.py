# -*- coding: utf-8 -*-
import argparse
import json
import os

import requests

from common import ROOT, get_task_output_dir


def fallback(report_data):
    return {
        "title": f"{report_data.get('task_title', '')} 审查分析报告",
        "executive_summary": [
            f"该任务共标准化 {report_data.get('flow_count', 0)} 条流水，命中流水 {report_data.get('matched_flow_count', 0)} 条，命中客户 {report_data.get('matched_customer_count', 0)} 个。",
            f"精确匹配 {report_data.get('exact_match_count', 0)} 条，脱敏匹配 {report_data.get('desensitized_match_count', 0)} 条，模糊匹配 {report_data.get('fuzzy_match_count', 0)} 条。",
            f"夜间交易 {report_data.get('night_transactions', {}).get('count', 0)} 条，金额 {report_data.get('night_transactions', {}).get('amount', '')}。",
        ],
        "sections": [
            {"title": "匹配情况分析", "content": ["当前为脚本兜底内容，接入大模型后会生成更完整的业务化解读。"]},
            {"title": "风险提示", "content": ["建议重点关注高频交易对手、夜间交易以及短时集中交易对象。"]},
        ],
        "conclusion": "根据当前结构化分析结果，建议优先复核命中频次高且交易行为异常的对象。",
    }


parser = argparse.ArgumentParser()
parser.add_argument("--task-id", required=True)
parser.add_argument("--api-base", default=os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"))
parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
args = parser.parse_args()

task_out = get_task_output_dir(args.task_id)
report_data = json.loads((task_out / "report_data.json").read_text(encoding="utf-8"))
target = task_out / "narrative.json"
prompt = (ROOT / "references" / "task_report_prompt.md").read_text(encoding="utf-8")

if not args.api_key:
    target.write_text(json.dumps(fallback(report_data), ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    raise SystemExit(0)

body = {
    "model": args.model,
    "messages": [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(report_data.get("narrative_input", {}), ensure_ascii=False, indent=2)},
    ],
    "temperature": 0.2,
    "max_tokens": 1600,
    "response_format": {"type": "json_object"},
}
headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}

try:
    response = requests.post(f"{args.api_base.rstrip('/')}/chat/completions", headers=headers, json=body, timeout=90)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    target.write_text(content, encoding="utf-8")
except Exception:
    target.write_text(json.dumps(fallback(report_data), ensure_ascii=False, indent=2), encoding="utf-8")

print(target)
