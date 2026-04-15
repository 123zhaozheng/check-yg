# -*- coding: utf-8 -*-
"""Unified audit skill exporter."""

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
    """导出统一审查 Skills 工程。"""

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
            expert_root = root / "expert_workflow"
            task_root.mkdir(parents=True, exist_ok=True)
            ref_root.mkdir(parents=True, exist_ok=True)
            expert_root.mkdir(parents=True, exist_ok=True)

            task_index = []
            assets_manifest = {"tasks": {}}
            for item in exported:
                task_info, task_assets = self._export_task_folder(task_root, item)
                task_index.append(task_info)
                assets_manifest["tasks"][task_info["task_id"]] = task_assets

            manifest, summary = self._build_board_metadata(exported, skipped)
            manifest["tasks"] = task_index
            manifest["resource_model"] = "统一Skills结构：单任务是一个任务目录，多任务是多个任务目录"

            self._write_json(ref_root / "board_manifest.json", manifest)
            self._write_json(ref_root / "board_summary.json", summary)
            self._write_json(ref_root / "assets_manifest.json", assets_manifest)
            self._write_text(ref_root / "workflow.md", self._build_workflow_reference())
            self._write_text(ref_root / "question_examples.md", self._build_question_examples())
            self._write_text(ref_root / "task_report_prompt.md", self._build_task_report_prompt())
            self._write_text(ref_root / "environment.md", self._build_environment_reference())
            self._write_text(ref_root / "reporting.md", self._build_reporting_reference())
            self._write_text(ref_root / "data_dictionary.md", self._build_data_dictionary())
            self._write_text(ref_root / "capability_model.md", self._build_capability_model())

            self._write_text(expert_root / "审查全流程.md", self._build_expert_workflow_markdown())
            self._write_text(expert_root / "专家经验库.md", self._build_expert_experience_markdown(summary))
            self._write_text(expert_root / "能力沉淀机制.md", self._build_capability_accumulation_markdown())
            self._write_json(expert_root / "审查维度清单.json", {"dimensions": self._build_dimension_catalog()})
            self._write_text(expert_root / "新维度沉淀问答模板.md", self._build_dimension_question_templates())
            self._write_text(expert_root / "能力沉淀记录.md", self._build_capability_log_template())

            self._write_text(root / "SKILL.md", self._build_skill_markdown())
            self._write_text(root / "agents" / "openai.yaml", self._build_openai_yaml())

            self._zip_dir(root, target)

        return target, {
            "exported_count": len(exported),
            "skipped_count": len(skipped),
            "skipped_tasks": skipped,
        }

    def _export_task_folder(self, task_root: Path, task_item: Dict) -> Tuple[Dict, Dict]:
        task_id = str(task_item.get("task_id", "") or "")
        task_title = str(task_item.get("task_title", "") or task_id)
        review = dict(task_item.get("review_data", {}) or {})
        task_dir = task_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        task_profile = self._build_task_profile(task_id, task_title, review)
        self._write_json(task_dir / "审查结果.json", review)
        self._write_json(task_dir / "任务画像.json", task_profile)

        final_excel_path = self._resolve_existing_path(
            review.get("final_flow_excel_path", ""),
            review.get("final_excel_path", ""),
            review.get("reviewed_flow_excel_path", ""),
            review.get("flow_excel_path", ""),
        )
        standardized_excel_path = self._resolve_existing_path(
            review.get("standardized_flow_excel_path", ""),
            review.get("normalized_flow_excel_path", ""),
        )

        copied_standardized = self._copy_optional_file(standardized_excel_path, task_dir / "标准化流水.xlsx")
        copied_final = self._copy_optional_file(final_excel_path, task_dir / "最终审查流水.xlsx")

        intermediate_payload = self._collect_intermediate_payload(review)
        if intermediate_payload:
            self._write_json(task_dir / "中间审查数据.json", intermediate_payload)

        evidence_items = self._export_evidence_assets(task_dir / "证据目录", review)
        if not evidence_items and (task_dir / "证据目录").exists():
            shutil.rmtree(task_dir / "证据目录")

        task_info = {
            "task_id": task_id,
            "task_title": task_title,
            "review_id": str(review.get("review_id", "") or ""),
            "review_time": str(review.get("review_time", "") or ""),
            "folder": f"审查任务目录/{task_id}",
            "standardized_excel_file": copied_standardized,
            "final_excel_file": copied_final,
            "total_matches": int(review.get("total_matches", 0) or 0),
            "matched_customers": int(review.get("matched_customers", 0) or 0),
            "review_amount": self._format_amount(float(review.get("total_amount", 0.0) or 0.0)),
        }
        task_assets = {
            "has_standardized_flow_excel": bool(copied_standardized),
            "has_final_flow_excel": bool(copied_final),
            "has_intermediate_audit_data": bool(intermediate_payload),
            "has_evidence_assets": bool(evidence_items),
            "standardized_flow_file": copied_standardized,
            "final_flow_file": copied_final,
            "intermediate_data_file": "中间审查数据.json" if intermediate_payload else "",
            "evidence_items": evidence_items,
        }
        return task_info, task_assets

    def _build_task_profile(self, task_id: str, task_title: str, review: Dict) -> Dict:
        match_type_counter = Counter()
        customer_counter = Counter()
        customer_amount = defaultdict(float)
        counterparty_counter = Counter()
        for match in review.get("matches", []) or []:
            match_type = str(match.get("match_type", "") or "").strip()
            customer_name = str(match.get("customer_name", "") or "").strip()
            counterparty_name = str(match.get("counterparty_name", "") or "").strip()
            if match_type:
                match_type_counter[match_type] += 1
            if customer_name:
                customer_counter[customer_name] += 1
                customer_amount[customer_name] += self._parse_amount(match.get("amount", ""))
            if counterparty_name:
                counterparty_counter[counterparty_name] += 1
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
            "top_counterparties": [
                {
                    "counterparty_name": name,
                    "transaction_count": count,
                }
                for name, count in counterparty_counter.most_common(10)
            ],
            "capabilities": [
                "完整审查链执行",
                "任务级问答",
                "证据级核验",
                "历史复盘",
                "新维度沉淀",
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
            "skill_type": "employee-customer-audit-unified-skill",
            "skill_name": "audit-unified-skill",
            "version": "3.0.0",
            "generated_at": datetime.now().isoformat(),
            "task_count": len(exported),
            "capabilities": [
                "统一Skills结构导出",
                "看板级问题回答",
                "任务级深度追问",
                "证据级核验",
                "单任务精美 HTML 报告生成",
                "完整审查链执行",
                "专家经验总结",
                "新维度能力沉淀",
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
            return f"审查统一Skills_{exported[0].get('task_id', 'task')}"
        return f"审查统一Skills_{len(exported)}项任务"

    @staticmethod
    def _build_skill_markdown() -> str:
        return """---
name: audit-unified-skill
description: 统一的员工客户流水审查 Skills。单任务时，审查任务目录下只有一个任务目录；多任务时，审查任务目录下包含多个任务目录。支持看板统计、任务级追问、证据核验、HTML 报告、完整审查链和能力沉淀。
---

# 统一审查 Skills

这个 Skill 的目标是直接执行能力，不是泛泛解释。

## 顶层模式与规则

这个 Skill 有四种顶层模式：

- **环境校验模式**：在做 Excel 分析、问答或报告生成前，先校验 Python 和必需依赖。
- **看板/任务问答模式**：回答整体统计问题，或定位某个任务后做深度追问。
- **完整审查链模式**：按专家工作流逐个步骤完成完整审查链。
- **能力沉淀模式**：当用户提出新的重要审查维度时，在完成分析后追问是否要沉淀到标准工作流中。

规则：
- 在做分析、问答或报告生成前，始终先执行 `python scripts/check_environment.py`
- 先读取 `references/assets_manifest.json` 判断某个任务有哪些可用资产，再决定读哪些文件
- 所有确定性的指标、聚合结果和图表数据，优先用 Python 脚本计算，不要让模型凭文字猜数量
- 对任务级证据问题，优先读取 `审查任务目录/<task_id>/最终审查流水.xlsx`；如果不存在，再如实说明该任务没有生成该表格，必要时回退其他已导出资料
- 单任务报告必须严格按三段式流程执行：数据构建 -> 文字分析生成 -> HTML 渲染
- 如果没有可用的 OpenAI 兼容接口密钥，允许使用兜底文字，但必须说明这是脚本生成的兜底分析
- 严禁编造指标；如果定位不到任务或数据缺失，要明确说明
- 如果用户提出新的重要审查点，例如夜间交易、重复流水特征、集中交易模式，在完成分析后必须追问：**是否将这个能力沉淀到完整审查工作流中，供后续类似任务复用？**

## 统一结构说明

这套 Skills 只有一种结构：

- `审查任务目录/` 下永远按任务编号组织资料
- 单任务时，里面只有一个任务目录
- 多任务时，里面有多个任务目录
- 每个任务目录根据实际情况放入：
  - `审查结果.json`
  - `任务画像.json`
  - `标准化流水.xlsx`（有则导出）
  - `最终审查流水.xlsx`（有则导出）
  - `中间审查数据.json`（有则导出）
  - `证据目录/`（有则导出）

## 这个 Skill 能做什么

- 回答看板级问题，例如“最近审核了多少个任务”“哪个任务命中最多”
- 按任务编号、审查编号或任务标题定位某一个任务
- 回答任务级问题，例如：
  - 这个任务命中多少条流水
  - 精确匹配/脱敏匹配/模糊匹配分别多少条
  - 夜间交易多少条、金额多少
  - 交易对手 Top 10 是谁
  - 命中客户 Top 10 是谁
- 生成单任务精美 HTML 报告
- 按 `expert_workflow/审查全流程.md` 执行完整审查链
- 结合历史任务做经验迁移与模式复盘
- 对新的重要审查维度输出能力沉淀提议

## 判断树

分三步判断：

1. **范围判断**：用户是在问整体看板，还是某一个任务？
2. **执行判断**：用户是要快速问答、完整审查链，还是生成报告？
3. **沉淀判断**：用户是否提出了一个值得纳入标准工作流的新维度？

## 工作流

1. 校验环境：
   - 执行 `python scripts/check_environment.py`
   - 如果失败，按 `references/environment.md` 处理
2. 确认范围：
   - 看板级 -> 读取 `references/board_summary.json`
   - 任务级 -> 执行 `python scripts/query_task_index.py 关键词`
3. 确认任务资产：
   - 读取 `references/assets_manifest.json`
   - 判断该任务是否存在标准化流水、最终审查流水、中间数据、证据目录
4. 任务级分析：
   - 执行 `python scripts/build_task_report_data.py --task-id <task_id>`
   - 读取 `output/task_reports/<task_id>/report_data.json`
5. 如需完整审查链：
   - 按 `expert_workflow/审查全流程.md` 的步骤逐步执行
6. 单任务报告生成：
   - 执行 `python scripts/build_task_report_data.py --task-id <task_id>`
   - 执行 `python scripts/generate_task_report_narrative.py --task-id <task_id>`
   - 执行 `python scripts/render_task_html_report.py --task-id <task_id>`
7. 新维度沉淀：
   - 如果用户提出新维度，先完成当前分析
   - 再追问是否要沉淀到标准工作流中
   - 参考 `expert_workflow/能力沉淀机制.md` 与 `expert_workflow/新维度沉淀问答模板.md`

## 资源地图

- `references/board_manifest.json`：导出的任务索引
- `references/board_summary.json`：看板汇总指标
- `references/assets_manifest.json`：每个任务的资产存在情况
- `references/workflow.md`：简版执行流程
- `references/environment.md`：依赖和环境说明
- `references/reporting.md`：报告内容和图表建议
- `references/question_examples.md`：示例问题
- `references/task_report_prompt.md`：大模型文字分析提示词
- `references/data_dictionary.md`：数据字典
- `references/capability_model.md`：统一能力模型说明
- `expert_workflow/审查全流程.md`：完整审查链
- `expert_workflow/专家经验库.md`：专家经验总结
- `expert_workflow/能力沉淀机制.md`：新能力沉淀规则
- `expert_workflow/审查维度清单.json`：维度清单
- `expert_workflow/新维度沉淀问答模板.md`：沉淀追问模板
- `expert_workflow/能力沉淀记录.md`：记录后续专家交互沉淀的新增能力与修改痕迹
- `审查任务目录/<task_id>/`：每个任务的真实资料目录

## 输出约束

- 不要用看板汇总代替任务级 Excel 事实
- 不要未经检查就假设某个任务一定存在 `最终审查流水.xlsx`
- 如果某个任务没有生成某个表格，要明确告诉用户该任务没有导出该表格
- 如果用了兜底文案，不要声称整份报告是模型生成的
- 不要编造缺失指标或系统未支持的异常数量
"""

    @staticmethod
    def _build_workflow_reference() -> str:
        return """# 工作流

1. 看板级统计：读取 `board_summary.json`
2. 任务定位：运行 `query_task_index.py`
3. 资产判断：读取 `assets_manifest.json`
4. 单任务分析：运行 `build_task_report_data.py`
5. 单任务报告：运行 `generate_task_report_narrative.py` + `render_task_html_report.py`
6. 完整审查链：参考 `expert_workflow/审查全流程.md`
7. 能力沉淀：参考 `expert_workflow/能力沉淀机制.md`
"""

    @staticmethod
    def _build_question_examples() -> str:
        return """# 示例问题

- 最近审核了多少个任务？
- 当前导出了哪些任务？
- 分析一下任务 20250328_101500
- 这个任务精确匹配和脱敏匹配分别多少条？
- 这个任务夜间交易有多少条？
- 这个任务有没有重复流水模式？
- 请按完整审查链审一下这个任务
- 帮我生成这个任务的精美 HTML 报告
- 把夜间交易审查沉淀到标准工作流里
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
    def _build_environment_reference() -> str:
        return """# 环境说明

## 必需运行环境

- PATH 中可调用的 Python
- `openpyxl`
- `requests`

## 校验命令

```bash
python scripts/check_environment.py
```

## 如果缺少 Python

- 安装 Python 3.10 及以上版本，并确保 `python` 已加入 PATH

## 如果缺少 `openpyxl`

这个包用于读取导出的任务 Excel。

```bash
python -m pip install openpyxl
```

## 如果缺少 `requests`

这个包用于在文字分析阶段调用 OpenAI 兼容接口。

```bash
python -m pip install requests
```
"""

    @staticmethod
    def _build_reporting_reference() -> str:
        return """# 报告说明

## 单任务报告内容

单任务报告建议至少包含：

- KPI 指标卡
- 业务化文字分析
- 匹配类型分布
- 月度交易金额趋势
- 重点交易对手
- 重点命中客户
- 夜间交易分布
- 证据明细行

## 业务表达重点

报告应重点解释：

- 任务规模
- 匹配结果
- 异常交易信号
- 主要交易对手
- 风险提示
- 实际复核建议
"""

    @staticmethod
    def _build_data_dictionary() -> str:
        return """# 数据字典

## 任务目录核心文件
- `审查结果.json`：结构化命中结果
- `任务画像.json`：任务级摘要
- `标准化流水.xlsx`：标准化后的分析表（有则导出）
- `最终审查流水.xlsx`：写回匹配信息后的事实表（有则导出）
- `中间审查数据.json`：中间审查数据（有则导出）
- `证据目录/`：证据类附件（有则导出）

## 重点字段
- 交易时间
- 金额
- 交易对手名
- 匹配用户
- 摘要
- 流水行号
"""

    @staticmethod
    def _build_capability_model() -> str:
        return """# 统一能力模型

这套 Skills 只有一种结构：
- 单任务时，`审查任务目录/` 下只有一个任务目录
- 多任务时，`审查任务目录/` 下有多个任务目录

也就是说，单任务是多任务结构的特例，不再区分两套不同的 Skills 思想。

每个任务目录按实际情况导出资料；没有的文件就不导出，后续回答时如实说明缺失。
"""

    @staticmethod
    def _build_expert_workflow_markdown() -> str:
        return """# 审查全流程

1. 先定位目标任务
2. 读取 `assets_manifest.json`，确认该任务有哪些真实资产
3. 读取任务画像，建立任务概览
4. 读取审查结果，确认命中客户、命中条数和匹配类型
5. 优先读取最终审查流水；如果没有，则回退到其他已导出资料
6. 按默认维度完成完整审查：
   - 基础规模与命中情况
   - 匹配类型分布
   - 交易对手集中度
   - 夜间交易
   - 同金额重复模式
   - 短时集中交易模式
   - 重点证据明细
7. 如有需要，再进入历史复盘，对比相似任务和高频风险信号
8. 输出结论时采用：结论 -> 证据 -> 建议 的顺序
9. 如果用户提出新的重要审查维度，必须追问是否要沉淀进标准工作流
10. 如果用户确认沉淀，则后续应修改 `expert_workflow/审查全流程.md`、`expert_workflow/审查维度清单.json`，并把本次变更追加记录到 `expert_workflow/能力沉淀记录.md`
"""

    @staticmethod
    def _build_expert_experience_markdown(summary: Dict) -> str:
        return f"""# 专家经验库

## 核心经验
- 先看规模，再看命中，再看证据
- 任务级证据问题优先看最终审查流水
- 异常问题优先从夜间交易、重复金额、集中交易、重点对手切入
- 如果任务缺某个表格，不要假设存在，要如实说明缺失
- 发现新维度后，不只当前分析，还要判断是否值得沉淀为标准能力

## 当前导出规模
- 已导出任务数：{summary.get('task_count', 0)}
- 命中总条数：{summary.get('total_matches', 0)}
- 命中客户总数：{summary.get('total_matched_customers', 0)}

## 经验迁移原则
- 可稳定复用的经验，优先写进标准工作流
- 只适用于个别任务的判断，不要直接沉淀成全局能力
- 新增维度时，要明确其数据依赖、判断逻辑和输出格式
"""

    @staticmethod
    def _build_capability_accumulation_markdown() -> str:
        return """# 能力沉淀机制

当用户或审计专家在交互中提出新的重要审查点时，智能体必须执行以下流程：

1. 先基于当前任务完成该维度分析
2. 再判断这个维度是否具有复用价值
3. 明确追问用户：是否将该能力沉淀到完整审查工作流中
4. 如果用户同意，输出结构化沉淀建议
5. 同时把沉淀结果追加记录到 `expert_workflow/能力沉淀记录.md`，作为后续专家经验扩展痕迹
6. 如该维度确认纳入标准工作流，应同步更新 `expert_workflow/审查全流程.md` 和 `expert_workflow/审查维度清单.json` 的对应内容

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
    def _build_dimension_catalog() -> List[Dict]:
        return [
            {"name": "基础规模与命中情况", "description": "统计总流水、命中流水、命中客户、总金额等基础指标。"},
            {"name": "匹配类型分布", "description": "统计精确匹配、脱敏匹配、模糊匹配的分布情况。"},
            {"name": "交易对手集中度", "description": "识别高频交易对手及其金额集中情况。"},
            {"name": "夜间交易", "description": "识别 22:00 到次日 06:00 的交易特征。"},
            {"name": "同金额重复模式", "description": "识别同日、同对手、同金额的重复交易模式。"},
            {"name": "短时集中交易模式", "description": "识别短时间内与同一交易对手的集中往来。"},
            {"name": "重点证据明细", "description": "围绕命中记录输出交易时间、金额、交易对手、匹配用户和流水行号。"},
            {"name": "历史相似模式提示", "description": "结合历史任务总结相似模式和常见风险信号。"},
        ]

    @staticmethod
    def _build_dimension_question_templates() -> str:
        return """# 新维度沉淀问答模板

- 这个审查点是否只适用于当前任务，还是值得沉淀为通用能力？
- 是否要将“夜间交易审查”加入默认完整审查链？
- 是否要将“重复流水特征识别”加入默认完整审查链？
- 这个维度应该插入在基础统计之后，还是证据核验之后？
- 这个维度依赖哪些数据字段？
- 以后类似任务是否都要默认执行这个维度？
- 如果本次确认沉淀，要不要同步更新审查全流程和维度清单？
"""

    @staticmethod
    def _build_capability_log_template() -> str:
        return """# 能力沉淀记录

这个文件用于记录后续用户、审计专家与智能体交互过程中新增或修改的审查能力。

## 使用规则
- 当用户确认某个新维度需要沉淀时，在这里追加记录
- 每条记录建议包含：日期、维度名称、业务价值、插入流程位置、依赖字段、变更说明
- 如果该维度已经正式纳入标准工作流，还应同步修改：
  - `审查全流程.md`
  - `审查维度清单.json`

## 记录模板
- 日期：
- 维度名称：
- 业务价值：
- 插入流程位置：
- 依赖字段：
- 变更说明：
- 是否已同步更新流程/维度清单：
"""

    @staticmethod
    def _build_openai_yaml() -> str:
        return """display_name: 统一审查技能
short_description: 支持统一任务结构、看板统计、任务问答、完整审查链和能力沉淀
default_prompt: 基于这个统一审查技能包，先定位用户问题对应的任务，再检查该任务有哪些真实资产，随后按完整审查链执行分析；如果用户提出新的重要审查维度，在完成分析后追问是否沉淀到标准工作流中。
"""

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
    def _collect_intermediate_payload(review: Dict) -> Dict:
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
            value = review.get(key)
            if value not in (None, "", [], {}):
                payload[key] = value
        return payload

    @staticmethod
    def _export_evidence_assets(evidence_dir: Path, review: Dict) -> List[Dict]:
        items = []
        evidence_paths = review.get("evidence_paths") or review.get("evidence_files") or []
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
