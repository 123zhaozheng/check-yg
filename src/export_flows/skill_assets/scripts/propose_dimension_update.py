# -*- coding: utf-8 -*-
import argparse

from common import get_output_dir, load_dimension_catalog, normalize_text, write_json

parser = argparse.ArgumentParser()
parser.add_argument("--dimension", required=True)
args = parser.parse_args()

dimension = args.dimension.strip()
catalog = load_dimension_catalog()
matched = None
for item in catalog.get("dimensions", []) or []:
    name = normalize_text(item.get("name", ""))
    description = normalize_text(item.get("description", ""))
    if not name:
        continue
    if dimension in name or name in dimension or dimension in description:
        matched = item
        break

if matched:
    payload = {
        "update_type": "supplement_existing_dimension",
        "dimension_name": dimension,
        "target_dimension_id": matched.get("id", ""),
        "target_dimension_name": matched.get("name", ""),
        "business_value": f"【{dimension}】更像是对既有维度【{matched.get('name', '')}】的补充，应优先补充该维度，而不是新增并行维度。",
        "recommended_catalog_update": {
            "fields_to_review": ["description", "required_fields", "decision_logic", "output_fields", "operator_script", "operator_name"],
            "suggestion": "在目标维度中补充新的判断规则、字段依赖或输出字段；如果当前算子无法覆盖，再扩展 operator_script 指向的 Python 算子。",
        },
        "operator_script": matched.get("operator_script", "scripts/run_review_dimensions.py"),
        "operator_name": matched.get("operator_name", ""),
        "ask_for_persistence": f"【{dimension}】看起来可以并入【{matched.get('name', '')}】。是否要补充这个已有维度，并同步完善对应算子？",
    }
else:
    normalized_id = "".join(ch.lower() if ch.isalnum() else "_" for ch in dimension).strip("_") or "new_dimension"
    payload = {
        "update_type": "add_new_dimension",
        "dimension_name": dimension,
        "dimension_id": normalized_id,
        "business_value": f"补强【{dimension}】这一审查视角，提高后续类似任务的复用价值。",
        "recommended_catalog_update": {
            "id": normalized_id,
            "name": dimension,
            "description": "待补充：说明这个维度识别什么风险或事实特征。",
            "default_enabled": False,
            "operator_script": "scripts/run_review_dimensions.py",
            "operator_name": normalized_id,
            "output_key": normalized_id,
            "data_dependencies": ["最终审查流水.xlsx"],
            "required_fields": ["交易时间", "金额", "交易对手名", "匹配用户", "流水行号"],
            "decision_logic": "待补充：明确筛选、聚合或阈值判断逻辑。",
            "output_fields": ["结论", "证据", "建议"],
            "can_be_promoted": True,
        },
        "operator_action": "需要在 scripts/run_review_dimensions.py 依赖的算子实现中新增 operator_name 对应逻辑，或新增独立脚本并回填 operator_script。",
        "ask_for_persistence": f"是否要将【{dimension}】作为新维度加入 references/审查维度清单.json，并补充对应 Python 算子？",
    }

target = get_output_dir() / "dimension_update_proposal.json"
write_json(target, payload)
print(target)
