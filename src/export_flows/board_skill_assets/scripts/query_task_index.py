# -*- coding: utf-8 -*-
import json
import sys

from common import find_task, list_tasks

keyword = "".join(sys.argv[1:]).strip()
if not keyword:
    for task in list_tasks():
        print(f"{task.get('task_id', '')}\t{task.get('task_title', '')}\t{task.get('total_matches', 0)}")
    raise SystemExit(0)

task = find_task(keyword)
if not task:
    print("未找到匹配任务")
    raise SystemExit(1)

print(json.dumps(task, ensure_ascii=False, indent=2))
