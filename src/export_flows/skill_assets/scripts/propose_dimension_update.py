# -*- coding: utf-8 -*-
import argparse

from common import get_output_dir, write_json

parser = argparse.ArgumentParser()
parser.add_argument("--dimension", required=True)
args = parser.parse_args()

dimension = args.dimension.strip()
payload = {
    "dimension_name": dimension,
    "business_value": f"补强【{dimension}】这一审查视角，提高后续类似任务的复用价值。",
    "workflow_position": "建议插入在基础统计完成后、证据核验前。",
    "required_fields": ["交易时间", "金额", "交易对手名", "匹配用户", "流水行号"],
    "recommended_logic": "先确认相关字段齐全，再完成当前分析，最后追问用户是否沉淀为标准能力。",
    "recommended_outputs": ["结论", "证据", "建议是否纳入标准工作流"],
    "ask_for_persistence": f"是否要将【{dimension}】沉淀到完整审查工作流中，供后续类似任务复用？",
}

target = get_output_dir() / "dimension_update_proposal.json"
write_json(target, payload)
print(target)
