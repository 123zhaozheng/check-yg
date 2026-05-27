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
            review_dimensions = self._build_dimension_catalog()

            self._write_json(root / "skill_manifest.json", manifest)
            self._write_json(current_dir / "审查结果.json", review_data)
            self._write_json(current_dir / "任务画像.json", current_summary)
            self._write_json(current_dir / "workflow_context.json", workflow_context)
            self._write_json(history_dir / "history_index.json", history_summary)
            self._write_json(references_dir / "assets_manifest.json", asset_manifest)
            self._write_json(references_dir / "审查维度清单.json", {"dimensions": review_dimensions})

            self._write_text(root / "README.md", self._build_readme(manifest, current_summary, history_summary, asset_manifest))
            self._write_text(root / "SKILL.md", self._build_skill_markdown())
            self._write_text(prompts_dir / "system_prompt.txt", self._build_system_prompt())
            self._write_text(prompts_dir / "question_templates.md", self._build_question_templates())
            self._write_text(prompts_dir / "review_workflow_prompt.md", self._build_review_workflow_prompt())
            self._write_text(prompts_dir / "dimension_expansion_prompt.md", self._build_dimension_expansion_prompt())
            self._write_text(prompts_dir / "evidence_answering_prompt.md", self._build_evidence_answering_prompt())
            self._write_text(prompts_dir / "report_generation_prompt.md", self._build_report_generation_prompt())
            self._write_text(references_dir / "data_dictionary.md", self._build_data_dictionary())
            self._write_text(expert_dir / "审查全流程.md", self._build_expert_workflow_markdown())

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
                "审查维度清单维护与算子扩展",
            ],
            "workflow": [
                "先读取 references/assets_manifest.json，确认当前任务可用资产",
                "再读取 references/审查维度清单.json，确认默认审查维度、算子脚本和输出字段",
                "读取 current_task/任务画像.json 与 current_task/审查结果.json，掌握任务概况与命中结果",
                "优先读取 current_task/最终审查流水.xlsx 做证据回答；若缺失则回退到 current_task/标准化流水.xlsx",
                "如需深度审查，按 expert_workflow/审查全流程.md 逐步执行",
                "若用户提出新的重要审查维度，先判断是否补充已有维度；确属新维度再补充清单并新增或完善算子",
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
            "dimension_catalog_file": "references/审查维度清单.json",
            "dimension_operator": "scripts/run_review_dimensions.py",
            "interaction_rules": [
                "先给结论，再给证据。",
                "如问题涉及命中或证据，优先引用最终审查流水。",
                "完整审查必须读取 references/审查维度清单.json，并按 default_enabled 维度逐个执行。",
                "如用户提出新的重要审查维度，先判断是否是已有维度的补充；如果是则补充该维度，如果不是则新增维度并完善算子。",
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
                "id": "basic_scope_hits",
                "name": "基础规模与命中情况",
                "description": "统计总流水、命中流水、命中客户、总金额等基础指标。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "basic_scope_hits",
                "output_key": "basic_scope_hits",
                "data_dependencies": ["任务画像.json", "审查结果.json", "最终审查流水.xlsx"],
                "required_fields": ["金额", "匹配用户"],
                "decision_logic": "汇总任务画像、审查结果与流水规模，输出整体命中率、命中金额和基础规模。",
                "output_fields": ["flow_count", "matched_flow_count", "customer_count", "matched_customer_count", "total_amount", "matched_amount"],
                "can_be_promoted": True,
            },
            {
                "id": "match_type_distribution",
                "name": "匹配类型分布",
                "description": "统计精确匹配、脱敏匹配、模糊匹配的分布情况。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "match_type_distribution",
                "output_key": "match_type_distribution",
                "data_dependencies": ["审查结果.json"],
                "required_fields": ["match_type"],
                "decision_logic": "按审查结果中的 match_type 聚合，观察命中类型结构。",
                "output_fields": ["match_type_distribution", "exact_match_count", "desensitized_match_count", "fuzzy_match_count"],
                "can_be_promoted": True,
            },
            {
                "id": "matched_customer_concentration",
                "name": "命中客户集中度",
                "description": "识别命中客户的命中笔数与金额集中情况。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "matched_customer_concentration",
                "output_key": "top_customers",
                "data_dependencies": ["最终审查流水.xlsx", "审查结果.json"],
                "required_fields": ["匹配用户", "金额"],
                "decision_logic": "按匹配用户聚合命中流水笔数和金额，输出排名靠前的命中客户。",
                "output_fields": ["customer_name", "match_count", "match_amount"],
                "can_be_promoted": True,
            },
            {
                "id": "counterparty_concentration",
                "name": "交易对手集中度",
                "description": "识别高频交易对手及其金额集中情况。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "counterparty_concentration",
                "output_key": "top_counterparties",
                "data_dependencies": ["最终审查流水.xlsx"],
                "required_fields": ["交易对手名", "金额", "交易时间"],
                "decision_logic": "按交易对手聚合交易次数、金额和时间跨度，识别高频或高金额对手。",
                "output_fields": ["counterparty_name", "transaction_count", "total_amount", "time_range"],
                "can_be_promoted": True,
            },
            {
                "id": "night_transactions",
                "name": "夜间交易",
                "description": "识别 22:00 到次日 06:00 的交易特征。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "night_transactions",
                "output_key": "night_transactions",
                "data_dependencies": ["最终审查流水.xlsx"],
                "required_fields": ["交易时间", "交易对手名", "金额", "摘要"],
                "decision_logic": "筛选交易时间在 22:00 至次日 06:00 的流水，汇总笔数、金额和代表性证据行。",
                "output_fields": ["count", "amount", "rows"],
                "can_be_promoted": True,
            },
            {
                "id": "monthly_trend",
                "name": "月度趋势",
                "description": "按月统计交易金额变化，辅助观察交易节奏和异常月份。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "monthly_trend",
                "output_key": "monthly_amount_series",
                "data_dependencies": ["最终审查流水.xlsx"],
                "required_fields": ["交易时间", "金额"],
                "decision_logic": "按交易月份聚合金额，输出月度序列供趋势判断。",
                "output_fields": ["labels", "amounts"],
                "can_be_promoted": True,
            },
            {
                "id": "same_amount_repeat",
                "name": "同金额重复模式",
                "description": "识别同日、同对手、同金额的重复交易模式。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "same_amount_repeat",
                "output_key": "same_amount_cases",
                "data_dependencies": ["最终审查流水.xlsx"],
                "required_fields": ["交易时间", "交易对手名", "金额"],
                "decision_logic": "按交易对手、日期、金额分组，筛选同组两笔及以上的重复交易。",
                "output_fields": ["counterparty_name", "transaction_date", "same_amount", "transaction_count"],
                "can_be_promoted": True,
            },
            {
                "id": "short_interval_cluster",
                "name": "短时集中交易模式",
                "description": "识别短时间内与同一交易对手的集中往来。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "short_interval_cluster",
                "output_key": "short_interval_cases",
                "data_dependencies": ["最终审查流水.xlsx"],
                "required_fields": ["交易时间", "交易对手名"],
                "decision_logic": "按交易对手排序交易时间，筛选 30 分钟内连续两笔及以上的集中交易。",
                "output_fields": ["counterparty_name", "transaction_count"],
                "can_be_promoted": True,
            },
            {
                "id": "evidence_rows",
                "name": "重点证据明细",
                "description": "围绕命中记录输出交易时间、金额、交易对手、匹配用户和流水行号。",
                "default_enabled": True,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "evidence_rows",
                "output_key": "evidence_rows",
                "data_dependencies": ["最终审查流水.xlsx", "审查结果.json"],
                "required_fields": ["流水行号", "匹配用户", "交易时间", "交易对手名", "金额", "摘要"],
                "decision_logic": "筛选已命中流水，输出可直接引用的证据字段。",
                "output_fields": ["流水行号", "匹配用户", "交易时间", "交易对手名", "金额", "摘要"],
                "can_be_promoted": True,
            },
            {
                "id": "historical_similarity",
                "name": "历史相似模式提示",
                "description": "结合历史审查材料总结相似模式和常见风险信号。",
                "default_enabled": False,
                "operator_script": "scripts/run_review_dimensions.py",
                "operator_name": "historical_similarity",
                "output_key": "historical_similarity",
                "data_dependencies": ["历史审查目录/history_index.json"],
                "required_fields": ["notable_dimensions"],
                "decision_logic": "仅在用户要求跨任务复盘时启用，统计历史任务中的高频关注维度。",
                "output_fields": ["history_review_count", "historical_focus_dimensions"],
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
- **单任务深度审查模式**：按审查全流程逐步完成完整审查链。
- **能力沉淀模式**：当用户提出新的重要审查维度时，先判断是否补充已有维度；确属新维度再沉淀为标准能力。

## 强制规则

- 先读取 `references/assets_manifest.json`，确认当前任务有哪些真实资产可用。
- 再读取 `references/审查维度清单.json`，确认默认审查维度、算子脚本、输出字段和数据依赖。
- 再读取 `current_task/任务画像.json` 与 `current_task/审查结果.json`。
- 涉及证据、命中记录、交易时间、金额、交易对手时，优先读取 `current_task/最终审查流水.xlsx`。
- 如果没有 `最终审查流水.xlsx`，再回退到 `current_task/标准化流水.xlsx`。
- 如果用户要求跨任务复盘，才读取 `历史审查目录/history_index.json` 与对应历史任务文件。
- 如果用户提出新的重要审查维度，必须先对照 `references/审查维度清单.json` 判断：能补充已有维度就补充该维度；确属新维度才新增维度，并同步补充或新增对应 Python 算子。
- 不得编造不存在的字段、证据或风险结论。

## 这个 Skill 能做什么

- 回答当前任务的基础统计问题
- 输出命中客户、交易对手、匹配类型分布
- 做夜间交易、重复交易、短时集中交易等维度分析
- 输出证据级回答，尽量带交易时间、金额、交易对手、匹配用户、流水行号
- 结合历史审查目录做模式复盘与经验迁移
- 当用户提出新维度时，对照维度清单生成补充或新增建议，并说明需要修改的算子

## 固定执行顺序

1. 运行 `python scripts/check_environment.py`
2. 运行 `python scripts/analyze_task_assets.py`
3. 读取 `references/审查维度清单.json`
4. 读取 `current_task/workflow_context.json`
5. 如需完整分析，运行 `python scripts/run_review_dimensions.py`
6. 如需汇总审查上下文，运行 `python scripts/build_review_context.py`
7. 如需针对问题做快速回答，运行 `python scripts/answer_review_question.py "你的问题"`
8. 如发现新的重要审查维度，运行 `python scripts/propose_dimension_update.py --dimension "维度名"`

## 能力沉淀模式

当用户提出新的重要审查点时：

1. 先基于当前资料完成该维度分析
2. 给出结论和证据
3. 对照 `references/审查维度清单.json` 判断它是已有维度的补充，还是全新的审查维度
4. 如果只是补充，则说明应补充哪个维度、补充哪些字段/规则/输出
5. 如果是新维度，再输出一份结构化沉淀建议，说明：
   - 维度名称
   - 业务价值
   - 是否纳入默认审查链
   - 依赖哪些字段和文件
   - 对应 Python 算子脚本
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
- `references/审查维度清单.json`：可扩展维度清单，也是完整审查的默认执行清单
- `prompts/`：系统提示、工作流提示和沉淀提示
- `scripts/`：环境检查、维度算子执行、上下文构建、问题回答和沉淀提案脚本
"""

    @staticmethod
    def _build_system_prompt() -> str:
        return """你是员工客户流水审查助手。

你的输入来自一个执行型审查 Skills 包，包含当前任务、历史审查目录、标准化流水、最终审查流水、审查维度清单、审查全流程与提示模板。

回答规则：
1. 先确认资产，再回答问题。
2. 再读取 references/审查维度清单.json，按清单理解默认维度和对应算子。
3. 优先依据 current_task 中的结构化资料回答。
4. 涉及证据时，优先回到最终审查流水逐条核验。
5. 如需跨任务复盘，才使用历史审查目录。
6. 回答顺序固定为：结论 -> 依据 -> 如有必要给出建议。
7. 若用户提出新的重要审查维度，先判断是否补充已有维度；确属新维度再建议新增维度与算子。
8. 若资料不足，明确说明“根据当前技能包资料无法确定”。
9. 不得编造未提供的客户身份、业务背景或交易用途。
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
2. 读取 references/审查维度清单.json
3. 读取 current_task/任务画像.json
4. 读取 current_task/审查结果.json
5. 优先使用 current_task/最终审查流水.xlsx 做证据和维度分析
6. 按审查维度清单中 default_enabled=true 的维度逐个审查；每个维度优先使用清单中的 operator_script
7. 输出基础结论、重点风险、证据明细和建议复核点
8. 如果用户提出新的重要维度，先判断是否补充已有维度；确属新维度再建议新增维度与算子
"""

    @staticmethod
    def _build_dimension_expansion_prompt() -> str:
        return """当用户提出新的重要审查维度时，不要只回答当前问题。

你必须额外完成两件事：
1. 读取 references/审查维度清单.json，判断它是已有维度的补充，还是新的审查维度
2. 如果是补充，说明应补充的维度 id/name、补充原因、需要增加的字段/逻辑/输出
3. 如果是新维度，说明是否建议纳入默认审查链，以及应新增或完善哪个 Python 算子

输出结构化沉淀建议时，包含：
- 维度名称
- 业务价值
- 是否纳入默认审查链
- 所需数据字段
- 对应 Python 算子脚本
- 输出字段
- 推荐判断逻辑
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
    def _build_data_dictionary() -> str:
        return """# 数据字典

## 主要文件
- `审查结果.json`：审查命中与匹配结果
- `任务画像.json`：任务级摘要信息
- `workflow_context.json`：执行上下文、资产边界与维度清单入口
- `标准化流水.xlsx`：标准化后的原始分析表
- `最终审查流水.xlsx`：写回匹配信息后的事实表
- `references/assets_manifest.json`：当前技能包可用资产清单
- `references/审查维度清单.json`：默认审查维度、数据依赖、算子脚本、输出字段和沉淀规则

## 重点字段
- 交易时间
- 金额
- 交易对手名
- 匹配用户
- 摘要
- 流水行号
"""

    @staticmethod
    def _build_expert_workflow_markdown() -> str:
        return """# 审查全流程

前提：用户必须明确指定要审查的任务；未指定任务时，先要求用户指定任务或使用当前技能包内的当前任务。

1. 先检查当前任务有哪些可用资产
2. 读取任务画像，快速建立任务概览
3. 读取审查结果，确认命中客户、命中条数和匹配类型
4. 优先读取最终审查流水，抽取证据明细
5. 读取 `references/审查维度清单.json`
6. 按清单中 `default_enabled=true` 的维度逐个审查；每个维度优先运行其 `operator_script`，并按照 `output_key` 读取结果
7. 如果需要，再进入历史复盘，对比近似任务和高频风险信号；历史类维度应按清单配置决定是否启用
8. 输出结论时采用：结论 -> 证据 -> 建议 的顺序
9. 如果用户提出新的重要审查维度，先对照清单判断是否补充已有维度；确属新维度时，补充 `references/审查维度清单.json`，并新增或完善对应 Python 算子
"""

    @staticmethod
    def _build_readme(manifest: Dict, current_summary: Dict, history_summary: Dict, asset_manifest: Dict) -> str:
        return f"""# 审查 Skills 包说明

## 包定位
这是一个面向员工客户流水审查场景的执行型知识包。它保留当前任务结果，并用审查维度清单驱动完整审查链与后续能力沉淀。

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
- `expert_workflow/`：完整审查链
- `prompts/`：系统提示、工作流提示和能力扩展提示
- `references/`：资产清单、审查维度清单和数据字典
- `scripts/`：环境检查、维度算子执行、上下文构建、问题回答与维度沉淀提案
- `SKILL.md`：执行总入口

## 推荐使用方式
1. 先加载 `SKILL.md` 与 `prompts/system_prompt.txt`
2. 再读取 `references/assets_manifest.json`
3. 再读取 `references/审查维度清单.json`
4. 然后按 `expert_workflow/审查全流程.md` 执行
5. 如用户提出新维度，按 `prompts/dimension_expansion_prompt.md` 处理
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
