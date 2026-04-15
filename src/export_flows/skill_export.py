# -*- coding: utf-8 -*-
"""
Skills bundle exporter.

导出一个可供外部智能问答/Agent 使用的标准化技能包，包含：
1. 当前审查任务的结构化结果、报告、标准化流水 Excel
2. 历史审查目录（历史 JSON + 可用的标准化 Excel）
3. 固定工作流说明，确保后续问答稳定、可控
"""

import json
import logging
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import get_config
from ..core.review_history import ReviewHistoryManager

logger = logging.getLogger(__name__)


class SkillsExporter:
    """导出审查技能包。"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.review_history = ReviewHistoryManager(self.config.config_dir / "reviews")
        self.template_root = Path(__file__).resolve().parent / "skill_assets"

    def export_bundle(
        self,
        review_result,
        task_title: str = "",
        task_id: str = "",
        report_text: str = "",
        output_path: Optional[str] = None,
    ) -> Path:
        if not review_result:
            raise ValueError("当前没有可导出的审查结果")

        bundle_name = f"审查Skills包_{task_id or getattr(review_result, 'review_id', '')}"
        target_path = Path(output_path or (self.config.reports_folder / f"{bundle_name}.zip"))
        if target_path.suffix.lower() != ".zip":
            target_path = target_path.with_suffix(".zip")
        target_path.parent.mkdir(parents=True, exist_ok=True)

        review_data = review_result.to_dict()

        with tempfile.TemporaryDirectory(prefix="audit_skills_") as tmp_dir:
            root = Path(tmp_dir) / bundle_name
            root.mkdir(parents=True, exist_ok=True)
            if self.template_root.exists():
                shutil.copytree(self.template_root, root, dirs_exist_ok=True)

            current_dir = root / "current_task"
            history_dir = root / "历史审查目录"
            prompts_dir = root / "prompts"
            expert_dir = root / "expert_workflow"
            references_dir = root / "references"
            current_dir.mkdir(parents=True, exist_ok=True)
            history_dir.mkdir(parents=True, exist_ok=True)
            prompts_dir.mkdir(parents=True, exist_ok=True)
            expert_dir.mkdir(parents=True, exist_ok=True)
            references_dir.mkdir(parents=True, exist_ok=True)

            manifest = self._build_manifest(review_result, task_title, task_id)
            current_summary = self._build_current_summary(review_result, task_title, task_id)
            current_assets, asset_manifest = self._export_current_assets(current_dir, review_result, review_data, report_text)
            workflow_context = self._build_workflow_context(manifest, current_summary, current_assets)
            history_summary = self._export_history_assets(history_dir, exclude_review_id=manifest["review_id"])
            expert_dimensions = self._build_dimension_catalog()

            self._write_json(root / "skill_manifest.json", manifest)
            self._write_json(current_dir / "审查结果.json", review_data)
            self._write_json(current_dir / "任务画像.json", current_summary)
            self._write_json(current_dir / "workflow_context.json", workflow_context)
            self._write_json(history_dir / "history_index.json", history_summary)
            self._write_json(references_dir / "assets_manifest.json", asset_manifest)
            self._write_json(expert_dir / "审查维度清单.json", {"dimensions": expert_dimensions})

            self._write_text(root / "README.md", self._build_readme(manifest, current_summary, history_summary, asset_manifest))
            self._write_text(root / "SKILL.md", self._build_skill_markdown())
            self._write_text(prompts_dir / "system_prompt.txt", self._build_system_prompt())
            self._write_text(prompts_dir / "question_templates.md", self._build_question_templates())
            self._write_text(prompts_dir / "review_workflow_prompt.md", self._build_review_workflow_prompt())
            self._write_text(prompts_dir / "dimension_expansion_prompt.md", self._build_dimension_expansion_prompt())
            self._write_text(prompts_dir / "evidence_answering_prompt.md", self._build_evidence_answering_prompt())
            self._write_text(prompts_dir / "report_generation_prompt.md", self._build_report_generation_prompt())
            self._write_text(references_dir / "workflow_reference.md", self._build_workflow_reference())
            self._write_text(references_dir / "data_dictionary.md", self._build_data_dictionary())
            self._write_text(references_dir / "audit_best_practices.md", self._build_audit_best_practices())
            self._write_text(expert_dir / "审查全流程.md", self._build_expert_workflow_markdown())
            self._write_text(expert_dir / "专家经验库.md", self._build_expert_experience_markdown(history_summary))
            self._write_text(expert_dir / "能力沉淀机制.md", self._build_capability_accumulation_markdown())
            self._write_text(expert_dir / "新维度沉淀问答模板.md", self._build_dimension_question_templates())

            self._zip_directory(root, target_path)

        logger.info("Skills bundle exported to %s", target_path)
        return target_path

    def _export_current_assets(
        self,
        current_dir: Path,
        review_result,
        review_data: Dict,
        report_text: str,
    ) -> Tuple[Dict, Dict]:
        (current_dir / "审查报告.txt").write_text(
            str(report_text or "").strip() or "当前任务尚未生成报告文本。",
            encoding="utf-8",
        )

        standardized_path = self._resolve_existing_path(
            getattr(review_result, "flow_excel_path", ""),
            review_data.get("flow_excel_path", ""),
        )
        final_path = self._resolve_existing_path(
            review_data.get("final_flow_excel_path", ""),
            review_data.get("final_excel_path", ""),
            review_data.get("reviewed_flow_excel_path", ""),
        )
        if not final_path and standardized_path:
            final_path = standardized_path

        copied_standardized = self._copy_optional_file(standardized_path, current_dir / "标准化流水.xlsx")
        copied_final = self._copy_optional_file(final_path, current_dir / "最终审查流水.xlsx")

        intermediate_payload = self._collect_intermediate_payload(review_data)
        if intermediate_payload:
            self._write_json(current_dir / "中间审查数据.json", intermediate_payload)

        evidence_dir = current_dir / "证据目录"
        evidence_items = self._export_evidence_assets(evidence_dir, review_data)
        if not evidence_items and evidence_dir.exists():
            shutil.rmtree(evidence_dir)

        current_assets = {
            "has_standardized_flow_excel": bool(copied_standardized),
            "has_final_flow_excel": bool(copied_final),
            "has_intermediate_audit_data": bool(intermediate_payload),
            "has_evidence_assets": bool(evidence_items),
            "report_file": "审查报告.txt",
            "standardized_flow_file": copied_standardized,
            "final_flow_file": copied_final,
            "intermediate_data_file": "中间审查数据.json" if intermediate_payload else "",
            "evidence_items": evidence_items,
        }
        asset_manifest = {
            "current_task": current_assets,
            "history_review_count": 0,
            "notes": [
                "证据类问题优先读取最终审查流水.xlsx；如不存在则回退到标准化流水.xlsx。",
                "若用户提出新的重要审查维度，完成当前分析后要追问是否沉淀到标准审查工作流。",
            ],
        }
        return current_assets, asset_manifest

    def _build_manifest(self, review_result, task_title: str, task_id: str) -> Dict:
        review_id = str(getattr(review_result, "review_id", "") or "").strip()
        effective_task_id = str(task_id or review_id or "").strip()
        return {
            "bundle_type": "employee_customer_audit_skill",
            "bundle_version": "2.0.0",
            "task_title": str(task_title or effective_task_id or "审查任务"),
            "task_id": effective_task_id,
            "review_id": review_id,
            "review_time": str(getattr(review_result, "review_time", "") or ""),
            "generated_from": "report_page",
            "workflow_modes": [
                "环境校验模式",
                "单任务问答模式",
                "单任务深度审查模式",
                "能力沉淀模式",
            ],
            "capabilities": [
                "完整审查链执行",
                "证据级核验",
                "风险画像生成",
                "跨历史案例复盘对比",
                "专家经验沉淀与工作流扩展",
            ],
            "workflow": [
                "先读取 references/assets_manifest.json，确认当前任务可用资产",
                "读取 current_task/任务画像.json 与 current_task/审查结果.json，掌握任务概况与命中结果",
                "优先读取 current_task/最终审查流水.xlsx 做证据回答；若缺失则回退到 current_task/标准化流水.xlsx",
                "如需深度审查，按 expert_workflow/审查全流程.md 逐步执行",
                "若用户提出新的重要审查维度，完成分析后要询问是否沉淀到完整审查工作流中",
            ],
        }

    def _build_current_summary(self, review_result, task_title: str, task_id: str) -> Dict:
        matches = list(getattr(review_result, "matches", []) or [])
        match_type_counter = Counter()
        customer_counter = Counter()
        customer_amount = defaultdict(float)
        counterparty_counter = Counter()

        for match in matches:
            match_type_counter[str(getattr(match, "match_type", "") or "")] += 1
            customer_name = str(getattr(match, "customer_name", "") or "")
            counterparty_name = str(getattr(match, "counterparty_name", "") or "")
            customer_counter[customer_name] += 1
            counterparty_counter[counterparty_name] += 1
            customer_amount[customer_name] += self._parse_amount(getattr(match, "amount", ""))

        top_customers = [
            {
                "customer_name": name,
                "match_count": count,
                "match_amount": self._format_amount(customer_amount.get(name, 0.0)),
            }
            for name, count in customer_counter.most_common(10)
            if name
        ]
        top_counterparties = [
            {"counterparty_name": name, "transaction_count": count}
            for name, count in counterparty_counter.most_common(10)
            if name
        ]

        return {
            "task_title": str(task_title or getattr(review_result, "review_id", "") or ""),
            "task_id": str(task_id or getattr(review_result, "review_id", "") or ""),
            "review_time": str(getattr(review_result, "review_time", "") or ""),
            "total_customers": int(getattr(review_result, "total_customers", 0) or 0),
            "matched_customers": int(getattr(review_result, "matched_customers", 0) or 0),
            "total_matches": int(getattr(review_result, "total_matches", 0) or 0),
            "total_amount": self._format_amount(float(getattr(review_result, "total_amount", 0.0) or 0.0)),
            "match_type_distribution": dict(match_type_counter),
            "top_customers": top_customers,
            "top_counterparties": top_counterparties,
            "capabilities": [
                "完整审查链执行",
                "流水详细分析",
                "重点对象追问",
                "风险画像生成",
                "跨历史任务对比",
                "基于最终审查流水的证据回答",
                "新审查维度沉淀提议",
            ],
        }

    def _build_workflow_context(self, manifest: Dict, current_summary: Dict, current_assets: Dict) -> Dict:
        return {
            "task_id": manifest.get("task_id", ""),
            "task_title": manifest.get("task_title", ""),
            "review_id": manifest.get("review_id", ""),
            "review_time": manifest.get("review_time", ""),
            "available_assets": current_assets,
            "recommended_review_dimensions": [
                "基础规模与命中情况",
                "匹配类型分布",
                "命中客户集中度",
                "交易对手集中度",
                "夜间交易",
                "月度趋势",
                "同金额重复模式",
                "短时集中交易模式",
                "重点证据明细",
                "历史相似模式提示",
            ],
            "interaction_rules": [
                "先给结论，再给证据。",
                "如问题涉及命中或证据，优先引用最终审查流水。",
                "如用户提出新的重要审查维度，完成分析后追问是否沉淀为标准能力。",
            ],
            "profile_snapshot": current_summary,
        }

    def _export_history_assets(self, history_dir: Path, exclude_review_id: str = "") -> Dict:
        history_items: List[Dict] = []
        for item in self.review_history.list_reviews():
            review_id = str(item.get("review_id", "") or "")
            if not review_id or review_id == exclude_review_id:
                continue

            detail = self.review_history.load_review(review_id)
            if not detail:
                continue

            review_folder = history_dir / review_id
            review_folder.mkdir(parents=True, exist_ok=True)
            self._write_json(review_folder / "审查结果.json", detail)
            self._write_json(review_folder / "任务画像.json", self._build_history_profile(detail))

            standardized_path = self._resolve_existing_path(detail.get("standardized_flow_excel_path", ""), detail.get("flow_excel_path", ""))
            final_path = self._resolve_existing_path(
                detail.get("final_flow_excel_path", ""),
                detail.get("final_excel_path", ""),
                detail.get("reviewed_flow_excel_path", ""),
                detail.get("flow_excel_path", ""),
            )
            copied_standardized = self._copy_optional_file(standardized_path, review_folder / "标准化流水.xlsx")
            copied_final = self._copy_optional_file(final_path, review_folder / "最终审查流水.xlsx")

            history_items.append({
                "review_id": review_id,
                "review_time": str(detail.get("review_time", "") or ""),
                "flow_excel_path": str(detail.get("flow_excel_path", "") or ""),
                "total_customers": int(detail.get("total_customers", 0) or 0),
                "matched_customers": int(detail.get("matched_customers", 0) or 0),
                "total_matches": int(detail.get("total_matches", 0) or 0),
                "total_amount": self._format_amount(float(detail.get("total_amount", 0.0) or 0.0)),
                "has_standardized_excel": bool(copied_standardized),
                "standardized_excel_file": copied_standardized,
                "has_final_excel": bool(copied_final),
                "final_excel_file": copied_final,
                "notable_dimensions": [
                    "匹配类型分布",
                    "夜间交易",
                    "重复交易模式",
                    "重点命中对象",
                ],
            })

        history_items.sort(key=lambda entry: entry.get("review_time", ""), reverse=True)
        return {
            "history_review_count": len(history_items),
            "history_reviews": history_items,
        }

    def _build_history_profile(self, detail: Dict) -> Dict:
        match_type_counter = Counter()
        customer_counter = Counter()
        for match in detail.get("matches", []) or []:
            match_type = str(match.get("match_type", "") or "").strip()
            customer_name = str(match.get("customer_name", "") or "").strip()
            if match_type:
                match_type_counter[match_type] += 1
            if customer_name:
                customer_counter[customer_name] += 1
        return {
            "review_id": str(detail.get("review_id", "") or ""),
            "review_time": str(detail.get("review_time", "") or ""),
            "total_customers": int(detail.get("total_customers", 0) or 0),
            "matched_customers": int(detail.get("matched_customers", 0) or 0),
            "total_matches": int(detail.get("total_matches", 0) or 0),
            "total_amount": self._format_amount(float(detail.get("total_amount", 0.0) or 0.0)),
            "match_type_distribution": dict(match_type_counter),
            "top_customers": [
                {"customer_name": name, "match_count": count}
                for name, count in customer_counter.most_common(10)
            ],
        }

    @staticmethod
    def _build_dimension_catalog() -> List[Dict]:
        return [
            {
                "name": "基础规模与命中情况",
                "description": "统计总流水、命中流水、命中客户、总金额等基础指标。",
                "data_dependencies": ["任务画像.json", "审查结果.json", "最终审查流水.xlsx"],
                "can_be_promoted": True,
            },
            {
                "name": "匹配类型分布",
                "description": "统计精确匹配、脱敏匹配、模糊匹配的分布情况。",
                "data_dependencies": ["审查结果.json"],
                "can_be_promoted": True,
            },
            {
                "name": "交易对手集中度",
                "description": "识别高频交易对手及其金额集中情况。",
                "data_dependencies": ["最终审查流水.xlsx"],
                "can_be_promoted": True,
            },
            {
                "name": "夜间交易",
                "description": "识别 22:00 到次日 06:00 的交易特征。",
                "data_dependencies": ["最终审查流水.xlsx"],
                "can_be_promoted": True,
            },
            {
                "name": "同金额重复模式",
                "description": "识别同日、同对手、同金额的重复交易模式。",
                "data_dependencies": ["最终审查流水.xlsx"],
                "can_be_promoted": True,
            },
            {
                "name": "短时集中交易模式",
                "description": "识别短时间内与同一交易对手的集中往来。",
                "data_dependencies": ["最终审查流水.xlsx"],
                "can_be_promoted": True,
            },
            {
                "name": "重点证据明细",
                "description": "围绕命中记录输出交易时间、金额、交易对手、匹配用户和流水行号。",
                "data_dependencies": ["最终审查流水.xlsx", "审查结果.json"],
                "can_be_promoted": True,
            },
            {
                "name": "历史相似模式提示",
                "description": "结合历史审查材料总结相似模式和常见风险信号。",
                "data_dependencies": ["历史审查目录/history_index.json"],
                "can_be_promoted": True,
            },
        ]

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def _zip_directory(source_dir: Path, target_zip: Path) -> None:
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(source_dir.parent))

    @staticmethod
    def _resolve_existing_path(*candidates: object) -> Optional[Path]:
        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text:
                continue
            path = Path(text).expanduser()
            if path.exists() and path.is_file():
                return path
        return None

    @staticmethod
    def _copy_optional_file(source: Optional[Path], target: Path) -> str:
        if not source or not source.exists():
            return ""
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target.name

    @staticmethod
    def _collect_intermediate_payload(review_data: Dict) -> Dict:
        keys = [
            "intermediate_data",
            "intermediate_review_data",
            "audit_trace",
            "evidence_summary",
            "review_steps",
            "match_candidates",
        ]
        payload = {}
        for key in keys:
            value = review_data.get(key)
            if value not in (None, "", [], {}):
                payload[key] = value
        return payload

    @staticmethod
    def _export_evidence_assets(evidence_dir: Path, review_data: Dict) -> List[Dict]:
        items = []
        evidence_paths = review_data.get("evidence_paths") or review_data.get("evidence_files") or []
        for index, raw_path in enumerate(evidence_paths, start=1):
            text = str(raw_path or "").strip()
            if not text:
                continue
            path = Path(text).expanduser()
            if not path.exists() or not path.is_file():
                continue
            evidence_dir.mkdir(parents=True, exist_ok=True)
            target = evidence_dir / f"{index:02d}_{path.name}"
            shutil.copy2(path, target)
            items.append({"name": target.name, "source": str(path)})
        return items

    @staticmethod
    def _build_skill_markdown() -> str:
        return """---
name: employee-customer-audit-skill
summary: 面向单任务员工客户流水审查的执行型 Skills，可按固定工作流完成完整审查链，并支持能力沉淀。
---

# 员工客户流水审查 Skills

这个 Skill 的目标不是泛泛解释，而是执行完整审查链。

## 顶层模式

这个 Skill 有四种顶层模式：

- **环境校验模式**：先检查本地脚本运行环境是否完整。
- **单任务问答模式**：回答当前任务的统计、证据和风险问题。
- **单任务深度审查模式**：按专家工作流逐步完成完整审查链。
- **能力沉淀模式**：当用户提出新的重要审查维度时，分析后追问是否沉淀为标准能力。

## 强制规则

- 先读取 `references/assets_manifest.json`，确认当前任务有哪些真实资产可用。
- 再读取 `current_task/任务画像.json` 与 `current_task/审查结果.json`。
- 涉及证据、命中记录、交易时间、金额、交易对手时，优先读取 `current_task/最终审查流水.xlsx`。
- 如果没有 `最终审查流水.xlsx`，再回退到 `current_task/标准化流水.xlsx`。
- 如果用户要求跨任务复盘，才读取 `历史审查目录/history_index.json` 与对应历史任务文件。
- 如果用户提出新的重要审查维度，例如夜间交易、重复流水特征、集中交易模式，在完成当前分析后，必须追问是否将该能力沉淀到完整审查工作流中。
- 不得编造不存在的字段、证据或风险结论。

## 这个 Skill 能做什么

- 回答当前任务的基础统计问题
- 输出命中客户、交易对手、匹配类型分布
- 做夜间交易、重复交易、短时集中交易等维度分析
- 输出证据级回答，尽量带交易时间、金额、交易对手、匹配用户、流水行号
- 结合历史审查目录做模式复盘与经验迁移
- 当用户提出新维度时，生成能力沉淀建议并询问是否纳入标准工作流

## 固定执行顺序

1. 运行 `python scripts/check_environment.py`
2. 运行 `python scripts/analyze_task_assets.py`
3. 读取 `current_task/workflow_context.json`
4. 如需完整分析，运行 `python scripts/build_review_context.py`
5. 如需专家经验总结，运行 `python scripts/build_expert_experience_summary.py`
6. 如需针对问题做快速回答，运行 `python scripts/answer_review_question.py "你的问题"`
7. 如发现新的重要审查维度，运行 `python scripts/propose_dimension_update.py --dimension "维度名"`

## 能力沉淀模式

当用户提出新的重要审查点时：

1. 先基于当前资料完成该维度分析
2. 给出结论和证据
3. 明确追问：**是否将这个能力沉淀到完整审查工作流中，供后续类似任务复用？**
4. 如果用户同意，再输出一份结构化沉淀建议，说明：
   - 维度名称
   - 业务价值
   - 插入工作流的哪个环节
   - 依赖哪些字段和文件
   - 推荐判断逻辑
   - 推荐输出格式

## 资源地图

- `current_task/审查结果.json`：结构化命中结果
- `current_task/任务画像.json`：任务级摘要
- `current_task/workflow_context.json`：执行上下文
- `current_task/标准化流水.xlsx`：标准化流水
- `current_task/最终审查流水.xlsx`：优先使用的事实来源
- `历史审查目录/history_index.json`：历史任务索引
- `expert_workflow/审查全流程.md`：完整审查链
- `expert_workflow/专家经验库.md`：经验总结
- `expert_workflow/能力沉淀机制.md`：新维度沉淀规则
- `expert_workflow/审查维度清单.json`：可扩展维度清单
- `prompts/`：系统提示、工作流提示和沉淀提示
- `scripts/`：环境检查、上下文构建、问题回答和沉淀提案脚本
"""

    @staticmethod
    def _build_system_prompt() -> str:
        return """你是员工客户流水审查助手。

你的输入来自一个执行型审查 Skills 包，包含当前任务、历史审查目录、标准化流水、最终审查流水、专家工作流与提示模板。

回答规则：
1. 先确认资产，再回答问题。
2. 优先依据 current_task 中的结构化资料回答。
3. 涉及证据时，优先回到最终审查流水逐条核验。
4. 如需跨任务复盘，才使用历史审查目录。
5. 回答顺序固定为：结论 -> 依据 -> 如有必要给出建议。
6. 若用户提出新的重要审查维度，完成当前分析后，必须追问是否沉淀到完整审查工作流中。
7. 若资料不足，明确说明“根据当前技能包资料无法确定”。
8. 不得编造未提供的客户身份、业务背景或交易用途。
"""

    @staticmethod
    def _build_question_templates() -> str:
        return """# 推荐提问模板

## 当前任务追问
- 请总结当前任务完整审查链的执行顺序。
- 请总结当前任务最值得关注的 5 个交易对象，并给出依据。
- 请按匹配用户维度统计命中笔数和金额。
- 请基于最终审查流水，解释某一条命中记录的上下文。

## 风险画像生成
- 请为当前任务生成一份风险画像，分为交易频次、交易金额、交易对象集中度、时间分布四部分。
- 请分析这个任务的夜间交易特征，并给出证据。
- 请指出最可疑的重复往来对象，并给出涉及的流水行号。

## 历史复盘
- 请对比当前任务和历史审查目录中最近 3 个任务的共同特征。
- 请总结历史案例中高频出现的可疑模式，并判断当前任务是否存在类似情况。

## 能力沉淀
- 请把“夜间交易审查”整理成一个可复用的标准审查维度。
- 请把“重复流水特征识别”沉淀到完整审查工作流中。
"""

    @staticmethod
    def _build_review_workflow_prompt() -> str:
        return """你现在要执行完整审查链，而不是只做简短问答。

执行顺序：
1. 检查 references/assets_manifest.json
2. 读取 current_task/任务画像.json
3. 读取 current_task/审查结果.json
4. 优先使用 current_task/最终审查流水.xlsx 做证据和维度分析
5. 输出基础结论、重点风险、证据明细和建议复核点
6. 如果用户提出新的重要维度，完成分析后追问是否沉淀为标准能力
"""

    @staticmethod
    def _build_dimension_expansion_prompt() -> str:
        return """当用户提出新的重要审查维度时，不要只回答当前问题。

你必须额外完成两件事：
1. 判断这个维度是否具有复用价值
2. 明确追问用户：是否将该能力沉淀到完整审查工作流中，供后续类似任务复用

如果用户同意，请输出结构化沉淀建议，包含：
- 维度名称
- 业务价值
- 工作流插入位置
- 所需数据字段
- 推荐判断逻辑
- 推荐输出字段
"""

    @staticmethod
    def _build_evidence_answering_prompt() -> str:
        return """你在回答证据类问题时，必须尽量引用以下字段：
- 交易时间
- 金额
- 交易对手名
- 匹配用户
- 流水行号

如果最终审查流水存在，优先从其中取证；否则回退到标准化流水。
"""

    @staticmethod
    def _build_report_generation_prompt() -> str:
        return """你要生成的是审查结论，不是泛泛总结。

请围绕以下维度输出：
- 任务规模
- 命中情况
- 异常交易特征
- 重点交易对手
- 重点命中客户
- 证据支撑
- 建议复核方向
"""

    @staticmethod
    def _build_workflow_reference() -> str:
        return """# 审查工作流参考

1. 资产检查：确认标准化流水、最终审查流水、中间审查数据、证据目录是否存在
2. 任务画像阅读：理解规模、命中数量和能力边界
3. 结果阅读：掌握匹配结果和重点命中对象
4. 证据核验：优先读取最终审查流水
5. 维度分析：夜间交易、重复金额、短时集中交易、交易对手集中度等
6. 历史复盘：必要时比对历史任务
7. 输出结论：先结论，再证据，再建议
8. 能力沉淀：如发现新重要维度，追问是否纳入标准工作流
"""

    @staticmethod
    def _build_data_dictionary() -> str:
        return """# 数据字典

## 主要文件
- `审查结果.json`：审查命中与匹配结果
- `任务画像.json`：任务级摘要信息
- `workflow_context.json`：执行上下文与推荐审查维度
- `标准化流水.xlsx`：标准化后的原始分析表
- `最终审查流水.xlsx`：写回匹配信息后的事实表

## 重点字段
- 交易时间
- 金额
- 交易对手名
- 匹配用户
- 摘要
- 流水行号
"""

    @staticmethod
    def _build_audit_best_practices() -> str:
        return """# 审查链最佳实践

这套基础审查链默认覆盖以下高价值维度：
- 基础规模与命中情况
- 匹配类型分布
- 命中客户集中度
- 交易对手集中度
- 夜间交易
- 月度趋势
- 同金额重复模式
- 短时集中交易模式
- 重点证据明细
- 历史相似模式提示

这些维度参考了交易监测、异常交易识别和审计复核中的常见经验，适合作为完整审查链的第一版基础能力。
"""

    @staticmethod
    def _build_expert_workflow_markdown() -> str:
        return """# 审查全流程

1. 先检查当前任务有哪些可用资产
2. 读取任务画像，快速建立任务概览
3. 读取审查结果，确认命中客户、命中条数和匹配类型
4. 优先读取最终审查流水，抽取证据明细
5. 按默认维度完成一轮完整审查：
   - 基础规模与命中情况
   - 匹配类型分布
   - 交易对手集中度
   - 夜间交易
   - 同金额重复模式
   - 短时集中交易模式
   - 重点证据明细
6. 如果需要，再进入历史复盘，对比近似任务和高频风险信号
7. 输出结论时采用：结论 -> 证据 -> 建议 的顺序
8. 如果用户提出新的重要审查维度，必须追问是否要沉淀进标准工作流
"""

    @staticmethod
    def _build_expert_experience_markdown(history_summary: Dict) -> str:
        return f"""# 专家经验库

## 当前版本经验定位
这套 Skills 的目标，不只是回答问题，而是复用专家的完整审查思路。

## 经验重点
- 先看规模，再看命中，再看证据
- 证据问题优先回到最终审查流水
- 异常问题优先从夜间交易、重复金额、集中交易、重点对手切入
- 跨任务问题再读取历史审查目录，不要一开始就泛化
- 发现新维度后，不只当前分析，还要判断是否值得沉淀为标准能力

## 历史材料基础
当前已纳入历史审查任务数：{history_summary.get('history_review_count', 0)}

## 经验迁移原则
- 能稳定复用的经验，优先写进标准工作流
- 只适用于单个任务的判断，不要直接沉淀成全局能力
- 每次新增维度时，都要明确其数据依赖、判断逻辑和输出格式
"""

    @staticmethod
    def _build_capability_accumulation_markdown() -> str:
        return """# 能力沉淀机制

当用户或审计专家在交互中提出新的重要审查点时，智能体必须执行以下流程：

1. 先基于当前任务完成该维度分析
2. 再判断这个维度是否具有复用价值
3. 明确追问用户：是否将该能力沉淀到完整审查工作流中
4. 如果用户同意，输出结构化沉淀建议

## 适合沉淀的维度示例
- 夜间交易审查
- 重复流水特征识别
- 特定金额阈值识别
- 交易对手集中度分析
- 短时集中往来分析

## 沉淀建议应包含
- 维度名称
- 业务价值
- 插入工作流位置
- 所需数据字段
- 推荐判断逻辑
- 输出字段
- 是否建议纳入默认审查链
"""

    @staticmethod
    def _build_dimension_question_templates() -> str:
        return """# 新维度沉淀问答模板

- 这个审查点是否只适用于当前任务，还是值得沉淀为通用能力？
- 是否要将“夜间交易审查”加入默认完整审查链？
- 是否要将“重复流水特征识别”加入默认完整审查链？
- 这个维度应该插入在基础统计之后，还是证据核验之后？
- 这个维度依赖哪些数据字段？
- 以后类似任务是否都要默认执行这个维度？
"""

    @staticmethod
    def _build_readme(manifest: Dict, current_summary: Dict, history_summary: Dict, asset_manifest: Dict) -> str:
        return f"""# 审查 Skills 包说明

## 包定位
这是一个面向员工客户流水审查场景的执行型知识包。它不仅保留当前任务结果，还提供完整审查链、专家经验目录和能力沉淀机制。

## 当前任务
- 任务标题：{manifest.get('task_title', '')}
- 任务编号：{manifest.get('task_id', '')}
- 审查批次：{manifest.get('review_id', '')}
- 审查时间：{manifest.get('review_time', '')}
- 匹配条数：{current_summary.get('total_matches', 0)}
- 命中客户：{current_summary.get('matched_customers', 0)}
- 历史审查数量：{history_summary.get('history_review_count', 0)}

## 当前任务资产
- 标准化流水：{('有' if asset_manifest.get('current_task', {}).get('has_standardized_flow_excel') else '无')}
- 最终审查流水：{('有' if asset_manifest.get('current_task', {}).get('has_final_flow_excel') else '无')}
- 中间审查数据：{('有' if asset_manifest.get('current_task', {}).get('has_intermediate_audit_data') else '无')}
- 证据目录：{('有' if asset_manifest.get('current_task', {}).get('has_evidence_assets') else '无')}

## 目录说明
- `current_task/`：当前任务结构化结果、Excel、报告与执行上下文
- `历史审查目录/`：历史审查沉淀，用于跨案例复盘与经验迁移
- `expert_workflow/`：完整审查链、专家经验库、能力沉淀机制
- `prompts/`：系统提示、工作流提示和能力扩展提示
- `references/`：资产清单、工作流参考、数据字典和审查链最佳实践
- `scripts/`：环境检查、上下文构建、问题回答与维度沉淀提案
- `SKILL.md`：执行总入口

## 推荐使用方式
1. 先加载 `SKILL.md` 与 `prompts/system_prompt.txt`
2. 再读取 `references/assets_manifest.json`
3. 然后按 `expert_workflow/审查全流程.md` 执行
4. 如用户提出新维度，按 `expert_workflow/能力沉淀机制.md` 处理
"""

    @staticmethod
    def _parse_amount(amount_value: object) -> float:
        text = str(amount_value or "").strip()
        if not text:
            return 0.0
        clean = (
            text.replace(",", "")
            .replace("￥", "")
            .replace("¥", "")
            .replace("元", "")
            .replace("+", "")
            .replace("-", "")
        )
        try:
            return abs(float(clean))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _format_amount(value: float) -> str:
        return f"¥{value:,.2f}"
