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
from typing import Dict, List, Optional

from ..config import get_config
from ..core.review_history import ReviewHistoryManager

logger = logging.getLogger(__name__)


class SkillsExporter:
    """导出审查技能包。"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.review_history = ReviewHistoryManager(self.config.config_dir / "reviews")

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

        with tempfile.TemporaryDirectory(prefix="audit_skills_") as tmp_dir:
            root = Path(tmp_dir) / bundle_name
            root.mkdir(parents=True, exist_ok=True)

            current_dir = root / "current_task"
            history_dir = root / "历史审查目录"
            prompts_dir = root / "prompts"
            current_dir.mkdir(parents=True, exist_ok=True)
            history_dir.mkdir(parents=True, exist_ok=True)
            prompts_dir.mkdir(parents=True, exist_ok=True)

            manifest = self._build_manifest(review_result, task_title, task_id)
            current_summary = self._build_current_summary(review_result, task_title, task_id)
            history_summary = self._export_history_assets(history_dir, exclude_review_id=manifest["review_id"])

            self._write_json(root / "skill_manifest.json", manifest)
            self._write_json(current_dir / "审查结果.json", review_result.to_dict())
            self._write_json(current_dir / "任务画像.json", current_summary)
            self._write_json(history_dir / "history_index.json", history_summary)

            (current_dir / "审查报告.txt").write_text(
                str(report_text or "").strip() or "当前任务尚未生成报告文本。",
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                self._build_readme(manifest, current_summary, history_summary),
                encoding="utf-8",
            )
            (root / "SKILL.md").write_text(self._build_skill_markdown(), encoding="utf-8")
            (prompts_dir / "system_prompt.txt").write_text(self._build_system_prompt(), encoding="utf-8")
            (prompts_dir / "question_templates.md").write_text(self._build_question_templates(), encoding="utf-8")

            flow_excel_path = Path(str(getattr(review_result, "flow_excel_path", "") or "")).expanduser()
            if flow_excel_path.exists():
                shutil.copy2(flow_excel_path, current_dir / "标准化流水.xlsx")

            self._zip_directory(root, target_path)

        logger.info("Skills bundle exported to %s", target_path)
        return target_path

    def _build_manifest(self, review_result, task_title: str, task_id: str) -> Dict:
        review_id = str(getattr(review_result, "review_id", "") or "").strip()
        effective_task_id = str(task_id or review_id or "").strip()
        return {
            "bundle_type": "employee_customer_audit_skill",
            "bundle_version": "1.0.0",
            "task_title": str(task_title or effective_task_id or "审查任务"),
            "task_id": effective_task_id,
            "review_id": review_id,
            "review_time": str(getattr(review_result, "review_time", "") or ""),
            "generated_from": "report_page",
            "workflow": [
                "读取 current_task/标准化流水.xlsx 与 current_task/审查结果.json",
                "优先依据结构化结果回答，再回到标准化流水逐行核验",
                "若用户要求跨任务对比，再读取 历史审查目录/history_index.json 与对应历史文件",
                "输出结论时必须携带时间、金额、对象、流水行号等证据字段",
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
                "流水详细分析",
                "重点对象追问",
                "风险画像生成",
                "跨历史任务对比",
                "基于最终标准化流水的证据回答",
            ],
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

            flow_excel_path = Path(str(detail.get("flow_excel_path", "") or "")).expanduser()
            copied_excel = ""
            if flow_excel_path.exists():
                target_excel = review_folder / "标准化流水.xlsx"
                shutil.copy2(flow_excel_path, target_excel)
                copied_excel = target_excel.name

            history_items.append({
                "review_id": review_id,
                "review_time": str(detail.get("review_time", "") or ""),
                "flow_excel_path": str(detail.get("flow_excel_path", "") or ""),
                "total_customers": int(detail.get("total_customers", 0) or 0),
                "matched_customers": int(detail.get("matched_customers", 0) or 0),
                "total_matches": int(detail.get("total_matches", 0) or 0),
                "total_amount": self._format_amount(float(detail.get("total_amount", 0.0) or 0.0)),
                "has_standardized_excel": bool(copied_excel),
                "excel_file": copied_excel,
            })

        history_items.sort(key=lambda entry: entry.get("review_time", ""), reverse=True)
        return {
            "history_review_count": len(history_items),
            "history_reviews": history_items,
        }

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _zip_directory(source_dir: Path, target_zip: Path) -> None:
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(source_dir.parent))

    @staticmethod
    def _build_skill_markdown() -> str:
        return """# 员工客户流水审查 Skills

## 目标
把当前任务及历史审查结果转化为可复用的审查知识包，用于后续 Agent 问答、线索追问和风险画像分析。

## 固定工作流
1. 先读取 `current_task/任务画像.json`，了解任务摘要、命中分布和能力边界。
2. 再读取 `current_task/审查结果.json`，掌握匹配命中明细。
3. 若问题涉及原始证据，读取 `current_task/标准化流水.xlsx`，按行号核验。
4. 若问题涉及趋势、复用经验或跨案例对比，再读取 `历史审查目录/history_index.json` 与对应历史任务文件。
5. 输出必须优先给结论，再给证据，不得编造字段，不得跳出已提供资料。

## 支持任务
- 流水详细分析
- 命中客户与对手分布追问
- 风险画像生成
- 重点对象多轮追问
- 跨历史案例复盘对比

## 输出要求
- 所有结论尽量带 `交易时间`、`金额`、`交易对手名`、`匹配用户`、`流水行号`
- 若当前资料不足，直接说明“根据当前技能包资料无法确定”
- 避免泛化判断，优先引用结构化证据
"""

    @staticmethod
    def _build_system_prompt() -> str:
        return """你是员工客户流水审查助手。

你的输入来自一个固定结构的 Skills 包，包含当前任务、历史审查目录、标准化流水 Excel 和结构化匹配结果。

回答规则：
1. 必须优先依据 current_task 中的结构化资料回答。
2. 如用户要求具体证据，必须回到标准化流水逐条核验。
3. 如用户要求跨任务对比，才使用历史审查目录。
4. 回答顺序固定为：结论 -> 依据 -> 若有必要给出建议。
5. 若资料不足，明确说明“根据当前技能包资料无法确定”。
6. 不得编造未提供的客户身份、业务背景或交易用途。
"""

    @staticmethod
    def _build_question_templates() -> str:
        return """# 推荐提问模板

## 当前任务追问
- 请总结当前任务最值得关注的 5 个交易对象，并给出依据。
- 请按匹配用户维度统计命中笔数和金额。
- 请基于标准化流水，解释某一条命中记录的上下文。

## 风险画像生成
- 请为当前任务生成一份风险画像，分为交易频次、交易金额、交易对象集中度、时间分布四部分。
- 请指出最可疑的重复往来对象，并给出涉及的流水行号。

## 历史复盘
- 请对比当前任务和历史审查目录中最近 3 个任务的共同特征。
- 请总结历史案例中高频出现的可疑模式，并判断当前任务是否存在类似情况。
"""

    @staticmethod
    def _build_readme(manifest: Dict, current_summary: Dict, history_summary: Dict) -> str:
        return f"""# 审查 Skills 包说明

## 包定位
这是一个面向员工客户流水审查场景的可迁移知识包。它把一次审查过程沉淀为结构化资料，支持外部智能问答或 Agent 持续深挖。

## 当前任务
- 任务标题：{manifest.get("task_title", "")}
- 任务编号：{manifest.get("task_id", "")}
- 审查批次：{manifest.get("review_id", "")}
- 审查时间：{manifest.get("review_time", "")}
- 匹配条数：{current_summary.get("total_matches", 0)}
- 命中客户：{current_summary.get("matched_customers", 0)}
- 历史审查数量：{history_summary.get("history_review_count", 0)}

## 目录说明
- `current_task/`：当前任务的最终结构化结果、报告、标准化流水与任务画像
- `历史审查目录/`：历史审查沉淀，用于跨案例追问与经验迁移
- `prompts/`：推荐 system prompt 与问题模板
- `SKILL.md`：固定工作流说明

## 推荐使用方式
1. 先加载 `SKILL.md` 与 `prompts/system_prompt.txt`
2. 再加载 `current_task/` 下资料进行回答
3. 若需跨任务对比，再按需读取 `历史审查目录/`
4. 回答时始终引用证据字段，避免泛化结论
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
