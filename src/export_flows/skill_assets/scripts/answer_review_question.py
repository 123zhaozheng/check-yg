# -*- coding: utf-8 -*-
import argparse

from common import load_workflow_context, normalize_text

parser = argparse.ArgumentParser()
parser.add_argument("question")
args = parser.parse_args()

question = normalize_text(args.question)
context = load_workflow_context()

dimension_keywords = {
    "夜间": "夜间交易",
    "重复": "同金额重复模式",
    "集中": "短时集中交易模式",
    "对手": "交易对手集中度",
}

matched_dimension = ""
for keyword, dimension in dimension_keywords.items():
    if keyword in question:
        matched_dimension = dimension
        break

if "完整审查链" in question or "工作流" in question:
    print("建议按以下顺序执行：资产检查 -> 任务画像 -> 审查结果 -> 最终审查流水 -> 维度分析 -> 证据输出 -> 能力沉淀判断。")
elif matched_dimension:
    print(f"当前问题涉及【{matched_dimension}】。请先完成该维度分析；分析结束后，追问用户是否将该能力沉淀到完整审查工作流中。")
else:
    print("建议先读取 workflow_context.json 和审查结果，再结合最终审查流水进行回答。")
