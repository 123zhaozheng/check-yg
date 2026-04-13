# -*- coding: utf-8 -*-
import importlib
import shutil
import sys


def has_module(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


python_ok = shutil.which("python") is not None
openpyxl_ok = has_module("openpyxl")
requests_ok = has_module("requests")

print("环境校验结果：")
print(f"- python: {'正常' if python_ok else '缺失'}")
print(f"- openpyxl: {'正常' if openpyxl_ok else '缺失'}")
print(f"- requests: {'正常' if requests_ok else '缺失'}")

missing = []
if not python_ok:
    missing.append("python")
if not openpyxl_ok:
    missing.append("openpyxl")
if not requests_ok:
    missing.append("requests")

if missing:
    print("")
    print("缺少以下依赖：")
    for item in missing:
        print(f"- {item}")
    print("")
    print("建议执行：")
    if "openpyxl" in missing or "requests" in missing:
        print("python -m pip install openpyxl requests")
    sys.exit(1)

sys.exit(0)
