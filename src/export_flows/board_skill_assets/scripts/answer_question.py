# -*- coding: utf-8 -*-
import argparse

from common import find_task, load_summary

parser = argparse.ArgumentParser()
parser.add_argument("question")
args = parser.parse_args()

question = args.question.strip()
summary = load_summary()

if "多少个任务" in question or "最近审核了多少个任务" in question:
    print(f"最近审核并导出的任务数量为 {summary.get('task_count', 0)} 个。")
    raise SystemExit(0)

task = None
for token in question.replace("，", " ").replace("。", " ").split():
    task = find_task(token)
    if task:
        break

if task:
    print(f"已定位到任务 {task.get('task_id', '')}，建议先执行 build_task_report_data.py 再做详细分析。")
else:
    print("未能从问题中定位到具体任务，请明确任务编号或任务标题。")
