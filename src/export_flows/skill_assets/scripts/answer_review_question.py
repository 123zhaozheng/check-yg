# -*- coding: utf-8 -*-
import argparse

from common import load_dimension_catalog, load_workflow_context, normalize_text

parser = argparse.ArgumentParser()
parser.add_argument("question")
args = parser.parse_args()

question = normalize_text(args.question)
context = load_workflow_context()
catalog = load_dimension_catalog()

dimension_keywords = {}
for dimension in catalog.get("dimensions", []) or []:
    name = normalize_text(dimension.get("name", ""))
    if not name:
        continue
    dimension_keywords[name] = dimension
    for token in [name[:2], name.replace("模式", "").replace("分布", "").replace("集中度", "")]:
        token = normalize_text(token)
        if token:
            dimension_keywords[token] = dimension

matched_dimension = {}
for keyword, dimension in dimension_keywords.items():
    if keyword in question:
        matched_dimension = dimension
        break

if "完整审查链" in question or "工作流" in question:
    print("建议按以下顺序执行：资产检查 -> 读取审查维度清单 -> 任务画像 -> 审查结果 -> 最终审查流水 -> 按清单逐维度执行算子 -> 证据输出 -> 维度沉淀判断。")
elif matched_dimension:
    script = matched_dimension.get("operator_script", "scripts/run_review_dimensions.py")
    name = matched_dimension.get("name", "")
    output_key = matched_dimension.get("output_key", "")
    print(f"当前问题涉及【{name}】。请优先运行 `{script}`，并读取输出中的 `{output_key}`；如果用户提出的是该维度的新规则，补充该维度即可，如果清单中确无对应维度，再新增维度与算子。")
else:
    print("建议先读取 references/审查维度清单.json、workflow_context.json 和审查结果，再结合最终审查流水进行回答。")
