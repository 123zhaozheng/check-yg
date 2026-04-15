# -*- coding: utf-8 -*-
from common import get_output_dir, load_assets_manifest, write_json

payload = load_assets_manifest()
target = get_output_dir() / "assets_analysis.json"
write_json(target, payload)
print(target)
