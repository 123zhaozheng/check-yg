# -*- coding: utf-8 -*-
import argparse

from common import build_dimension_results, get_output_dir, write_json

parser = argparse.ArgumentParser()
parser.add_argument(
    "--include-disabled",
    action="store_true",
    help="同时执行审查维度清单中 default_enabled=false 的维度。",
)
args = parser.parse_args()

payload = build_dimension_results(include_disabled=args.include_disabled)
target = get_output_dir() / "dimension_results.json"
write_json(target, payload)
print(target)
