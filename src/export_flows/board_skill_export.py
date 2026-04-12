# -*- coding: utf-8 -*-
"""Board-level skill exporter."""

import json
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional, Tuple

from ..config import get_config
from ..core.review_history import ReviewHistoryManager


class BoardSkillExporter:
    """导出看板多任务 Skills 工程。"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.review_history = ReviewHistoryManager(self.config.config_dir / "reviews")
        self.template_root = Path(__file__).resolve().parent / "board_skill_assets"

    def export_board_skill(
        self,
        selected_tasks: List[Dict],
        output_path: Optional[str] = None,
    ) -> Tuple[Path, Dict]:
        picked = [dict(item) for item in (selected_tasks or []) if item.get("task_id")]
        if not picked:
            raise ValueError("未选择任何任务")

        exported, skipped = [], []
        for task in picked:
            task_id = str(task.get("task_id", "") or "").strip()
            review_data = self._find_review_data_for_task(task_id)
            if not review_data:
                skipped.append({
                    "task_id": task_id,
                    "task_title": str(task.get("title", "") or ""),
                    "reason": "未找到已完成的审查结果",
                })
                continue
            exported.append({
                "task_id": task_id,
                "task_title": str(task.get("title", "") or task_id),
                "review_data": review_data,
            })

        if not exported:
            raise ValueError("所选任务中没有可导出的审查结果")

        bundle_name = self._build_bundle_name(exported)
        target = Path(output_path or (self.config.reports_folder / f"{bundle_name}.zip"))
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")
        target.parent.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory(prefix="board_skill_") as tmp_dir:
            root = Path(tmp_dir) / bundle_name
            root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.template_root, root, dirs_exist_ok=True)

            task_root = root / "审查任务目录"
            ref_root = root / "references"
            task_index = [self._export_task_folder(task_root, item) for item in exported]
            manifest, summary = self._build_board_metadata(exported, skipped)
            manifest["tasks"] = task_index

            self._write_json(ref_root / "board_manifest.json", manifest)
            self._write_json(ref_root / "board_summary.json", summary)
            self._write_text(ref_root / "workflow.md", self._build_workflow_reference())
            self._write_text(ref_root / "question_examples.md", self._build_question_examples())
            self._write_text(ref_root / "task_report_prompt.md", self._build_task_report_prompt())
            self._write_text(root / "SKILL.md", self._build_skill_markdown())
            self._write_text(root / "agents" / "openai.yaml", self._build_openai_yaml())

            self._zip_dir(root, target)

        return target, {
            "exported_count": len(exported),
            "skipped_count": len(skipped),
            "skipped_tasks": skipped,
        }

    def _export_task_folder(self, task_root: Path, task_item: Dict) -> Dict:
        task_id = str(task_item.get("task_id", "") or "")
        task_title = str(task_item.get("task_title", "") or task_id)
        review = dict(task_item.get("review_data", {}) or {})
        task_dir = task_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(task_dir / "审查结果.json", review)
        self._write_json(task_dir / "任务画像.json", self._build_task_profile(task_id, task_title, review))

        copied_excel = ""
        flow_excel_path = Path(str(review.get("flow_excel_path", "") or "")).expanduser()
        if flow_excel_path.exists():
            copied_excel = "最终审查流水.xlsx"
            shutil.copy2(flow_excel_path, task_dir / copied_excel)

        return {
            "task_id": task_id,
            "task_title": task_title,
            "review_id": str(review.get("review_id", "") or ""),
            "review_time": str(review.get("review_time", "") or ""),
            "folder": f"审查任务目录/{task_id}",
            "final_excel_file": copied_excel,
            "total_matches": int(review.get("total_matches", 0) or 0),
            "matched_customers": int(review.get("matched_customers", 0) or 0),
            "review_amount": self._format_amount(float(review.get("total_amount", 0.0) or 0.0)),
        }

    def _build_task_profile(self, task_id: str, task_title: str, review: Dict) -> Dict:
        match_type_counter = Counter()
        customer_counter = Counter()
        customer_amount = defaultdict(float)
        for match in review.get("matches", []) or []:
            match_type = str(match.get("match_type", "") or "").strip()
            customer_name = str(match.get("customer_name", "") or "").strip()
            if match_type:
                match_type_counter[match_type] += 1
            if customer_name:
                customer_counter[customer_name] += 1
                customer_amount[customer_name] += self._parse_amount(match.get("amount", ""))
        return {
            "task_id": task_id,
            "task_title": task_title,
            "review_id": str(review.get("review_id", "") or ""),
            "review_time": str(review.get("review_time", "") or ""),
            "total_customers": int(review.get("total_customers", 0) or 0),
            "matched_customers": int(review.get("matched_customers", 0) or 0),
            "total_matches": int(review.get("total_matches", 0) or 0),
            "review_amount": self._format_amount(float(review.get("total_amount", 0.0) or 0.0)),
            "match_type_distribution": dict(match_type_counter),
            "top_customers": [
                {
                    "customer_name": name,
                    "match_count": count,
                    "match_amount": self._format_amount(customer_amount.get(name, 0.0)),
                }
                for name, count in customer_counter.most_common(10)
            ],
        }

    def _build_board_metadata(self, exported: List[Dict], skipped: List[Dict]) -> Tuple[Dict, Dict]:
        total_amount = 0.0
        total_matches = 0
        total_matched_customers = 0
        match_type_counter = Counter()
        for item in exported:
            review = item["review_data"]
            total_amount += float(review.get("total_amount", 0.0) or 0.0)
            total_matches += int(review.get("total_matches", 0) or 0)
            total_matched_customers += int(review.get("matched_customers", 0) or 0)
            for match in review.get("matches", []) or []:
                match_type = str(match.get("match_type", "") or "").strip()
                if match_type:
                    match_type_counter[match_type] += 1
        manifest = {
            "skill_type": "employee-customer-audit-board-skill",
            "skill_name": "audit-board-skill",
            "version": "2.0.0",
            "generated_at": datetime.now().isoformat(),
            "task_count": len(exported),
            "capabilities": [
                "回答看板级任务统计问题",
                "定位具体任务并读取最终审查流水",
                "回答任务级指标问题",
                "生成单任务精美 HTML 报告",
                "通过 OpenAI 兼容接口生成业务化文字分析",
            ],
            "skipped_tasks": skipped,
        }
        summary = {
            "task_count": len(exported),
            "total_matches": total_matches,
            "total_matched_customers": total_matched_customers,
            "total_review_amount": self._format_amount(total_amount),
            "match_type_distribution": dict(match_type_counter),
        }
        return manifest, summary

    def _find_review_data_for_task(self, task_id: str) -> Optional[Dict]:
        candidates = []
        for item in self.review_history.list_reviews():
            flow_excel_path = str(item.get("flow_excel_path", "") or "")
            stem = Path(flow_excel_path).stem
            if stem == f"流水_{task_id}" or task_id in flow_excel_path:
                detail = self.review_history.load_review(str(item.get("review_id", "") or ""))
                if detail:
                    candidates.append(detail)
        if not candidates:
            return None
        candidates.sort(
            key=lambda entry: str(entry.get("review_time", "") or entry.get("saved_at", "")),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _build_bundle_name(exported: List[Dict]) -> str:
        if len(exported) == 1:
            return f"审查看板Skills_{exported[0].get('task_id', 'task')}"
        return f"审查看板Skills_{len(exported)}项任务"

    @staticmethod
    def _build_skill_markdown() -> str:
        return """---
name: audit-board-skill
description: Use this skill when working with an exported employee-customer audit task bundle. It answers board-level questions such as “最近审核了多少个任务”, locates a task by task ID or task title, reads the final reviewed Excel with 匹配用户/匹配度 columns, computes task metrics with Python, answers task-level questions such as “这个任务审查了多少条流水/命中多少条/精确匹配多少条/夜间交易多少条”, and generates a polished single-task HTML report with charts and LLM-written business analysis.
---

# Audit Board Skill

这个 Skill 的目标不是泛泛解释，而是直接执行能力。

## 能力清单
1. 回答看板级问题
2. 回答单任务指标问题
3. 回答单任务证据追问
4. 生成单任务精美 HTML 报告
5. 使用大模型生成业务化文字分析

## 路由规则

### 看板级问题
- 读取 `references/board_manifest.json` 和 `references/board_summary.json`
- 必要时执行 `python scripts/count_board_tasks.py`
- 定位任务时执行 `python scripts/query_task_index.py 关键词`

### 单任务问题
- 先执行 `python scripts/build_task_report_data.py --task-id <task_id>`
- 再读取 `output/task_reports/<task_id>/report_data.json`
- 如需证据，回到 `审查任务目录/<task_id>/最终审查流水.xlsx`

### 单任务报告
- 执行 `python scripts/build_task_report_data.py --task-id <task_id>`
- 执行 `python scripts/generate_task_report_narrative.py --task-id <task_id>`
- 执行 `python scripts/render_task_html_report.py --task-id <task_id>`
- 输出：`output/task_reports/<task_id>/<task_id>_审查分析报告.html`

## 关键约束
- 必须优先使用 `最终审查流水.xlsx`
- 这是最终版 Excel，包含 `匹配用户` 和 `匹配度` 列
- 结论先行，证据随后
- 数据不足时，明确说明“根据当前导出的审查技能包资料无法确定”
"""

    @staticmethod
    def _build_workflow_reference() -> str:
        return """# Workflow

1. 看板级统计：读取 `board_summary.json`
2. 任务定位：运行 `query_task_index.py`
3. 单任务分析：运行 `build_task_report_data.py`
4. 单任务报告：运行 `generate_task_report_narrative.py` + `render_task_html_report.py`
"""

    @staticmethod
    def _build_question_examples() -> str:
        return """# 示例问题

- 最近审核了多少个任务？
- 当前导出了哪些任务？
- 分析一下任务 20250328_101500
- 这个任务总共标准化了多少条流水？
- 这个任务精确匹配和脱敏匹配分别多少条？
- 这个任务夜间交易有多少条？
- 帮我生成这个任务的精美 HTML 报告
"""

    @staticmethod
    def _build_task_report_prompt() -> str:
        return """你是一个审查报告撰写助手。

基于单个任务的结构化分析数据，输出业务可直接阅读的结论。

要求：
1. 用中文输出。
2. 只基于输入数据，不编造事实。
3. 重点解释任务规模、匹配情况、异常交易特征、主要交易对手和风险提示。
4. 风格正式、简洁、业务化。
5. 输出 JSON，字段固定为：title、executive_summary、sections、conclusion。
"""

    @staticmethod
    def _build_openai_yaml() -> str:
        return """display_name: 审查看板分析技能
short_description: 支持看板统计、单任务问答和单任务精美 HTML 报告生成
default_prompt: 基于这个审查看板技能包，先定位用户提问涉及的任务，再用脚本分析最终审查流水，并在需要时生成单任务精美报告。
"""

    @staticmethod
    def _zip_dir(source_dir: Path, target_zip: Path) -> None:
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(source_dir.parent))

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

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
