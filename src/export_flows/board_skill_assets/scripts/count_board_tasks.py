# -*- coding: utf-8 -*-
from common import list_tasks

tasks = list_tasks()
print(f"最近审核并导出的任务数量: {len(tasks)}")
for task in tasks:
    print(f"{task.get('task_id', '')}\t{task.get('task_title', '')}")
