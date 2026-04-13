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
            self._write_text(ref_root / "environment.md", self._build_environment_reference())
            self._write_text(ref_root / "reporting.md", self._build_reporting_reference())
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
description: 用于消费已导出的员工客户流水审查技能包。它可以回答“最近审核了多少个任务”这类看板级问题，也可以按任务编号或任务标题定位某一个任务，读取包含“匹配用户/匹配度”列的最终审查流水 Excel，通过 Python 脚本计算任务指标，回答“这个任务审查了多少条流水、命中多少条、精确匹配多少条、夜间交易多少条”这类问题，并为单个任务生成带图表和大模型业务分析文字的精美 HTML 报告。
---

# 审查看板技能

这个 Skill 的目标是直接执行能力，不是泛泛解释。

## 顶层模式与规则

这个 Skill 有且仅有三种顶层模式：

- **环境校验模式（永远优先）**：在做 Excel 分析、问答或报告生成前，先校验 Python 和必需依赖。
- **问答模式**：回答看板级问题或任务级问题，先定位任务，再读取最终审查流水，再用 Python 计算指标。
- **单任务报告模式**：针对某一个任务，先计算结构化指标，再调用 OpenAI 兼容模型生成业务化文字，最后渲染成 HTML 报告。

规则：
- 在做分析、问答或报告生成前，始终先执行 `python scripts/check_environment.py`
- 所有确定性的指标、聚合结果和图表数据，优先用 Python 脚本计算，不要让模型凭文字猜数量
- `审查任务目录/<task_id>/最终审查流水.xlsx` 是单任务分析的事实来源，必须优先使用
- 看板级 JSON 只用于看板汇总和任务发现，不能替代任务级 Excel 分析
- 单任务报告必须严格按三段式流程执行：数据构建 -> 文字分析生成 -> HTML 渲染
- 如果没有可用的 OpenAI 兼容接口密钥，允许使用兜底文字，但必须说明这是脚本生成的兜底分析
- 严禁编造指标；如果定位不到任务或数据缺失，要明确说明

## 这个 Skill 能做什么

- 回答看板级问题，例如“最近审核了多少个任务”“当前导出了哪些任务”“哪个任务命中最多”
- 按任务编号、审查编号或任务标题定位某一个任务
- 回答任务级问题，例如：
  - 这个任务标准化了多少条流水
  - 这个任务命中多少条流水
  - 精确匹配/脱敏匹配/模糊匹配分别多少条
  - 夜间交易多少条、金额多少
  - 每个月交易金额怎么分布
  - 交易对手 Top 10 是谁
  - 命中客户 Top 10 是谁
- 生成单任务精美 HTML 报告，报告中可包含：
  - KPI 指标卡
  - 月度交易金额趋势图
  - 匹配类型分布图
  - 交易对手 Top 图
  - 命中客户 Top 图
  - 夜间交易图
  - 证据明细表
  - 大模型生成的业务化文字分析

## 什么时候使用

- 用户问最近审核了多少个任务
- 用户想查看或比较已导出的审查任务
- 用户针对某一个任务做详细追问，并且希望回答有证据支撑
- 用户要求为某一个任务生成精美报告
- 用户要查询更适合通过最终 Excel 计算出来的指标

## 什么时候不要使用

- 用户只需要拷贝原始文件，不需要分析
- 用户想改主程序内部的审查逻辑或匹配逻辑，而不是消费导出的技能包
- 用户要处理的是与审查任务无关的通用文档
- 用户只需要一个简单看板概览，不需要任务级审查分析

## 判断树

分两步判断：

1. **意图判断**：用户是在问整个看板、某一个任务，还是要生成单任务报告？
2. **执行策略判断**：用户这个请求只需要索引定位，还是需要 Python 指标计算，还是需要完整报告生成？

意图判断：
- 如果用户问“最近审核了多少个任务”“当前有哪些任务”，这是 **看板级问答模式**
- 如果用户点名某个任务编号或标题，并追问数量、对手、趋势或异常，这是 **任务级问答模式**
- 如果用户说“帮我生成这个任务的精美报告”，这是 **单任务报告模式**

执行策略：
- 看板级问题：读取 `references/board_manifest.json`、`references/board_summary.json`，必要时运行轻量脚本
- 任务级问题：总是先生成或读取 `output/task_reports/<task_id>/report_data.json`
- 单任务报告：总是执行完整报告链路，并返回最终 HTML 文件路径

## 工作流

1. 校验环境：
   - 执行 `python scripts/check_environment.py`
   - 如果失败，按 `references/environment.md` 处理
2. 确认范围：
   - 看板级 -> 读取 `references/board_summary.json`
   - 任务级 -> 执行 `python scripts/query_task_index.py 关键词`
3. 任务级分析：
   - 执行 `python scripts/build_task_report_data.py --task-id <task_id>`
   - 读取 `output/task_reports/<task_id>/report_data.json`
4. 单任务报告生成：
   - 执行 `python scripts/build_task_report_data.py --task-id <task_id>`
   - 执行 `python scripts/generate_task_report_narrative.py --task-id <task_id>`
   - 执行 `python scripts/render_task_html_report.py --task-id <task_id>`
5. 校验输出：
   - 检查任务是否存在
   - 检查最终审查流水 Excel 是否存在
   - 检查指标数据是否为空
   - 检查 HTML 是否已成功生成
6. 如有生成报告，明确返回最终文件路径

## 环境校验

在执行任何实质分析前，都要先校验本地环境。

必需运行环境：
- PATH 中可用的 Python
- 用于读取最终审查 Excel 的 `openpyxl`
- 用于调用 OpenAI 兼容接口的 `requests`

推荐行为：
- 缺哪个依赖，就明确指出缺什么
- 引导查看 `references/environment.md`
- 没有 `openpyxl` 时，不要继续做 Excel 分析
- 没有 `requests` 时，不要继续做大模型文字生成

## 单任务报告流水线

单任务报告固定分三段：

1. **数据构建**：`scripts/build_task_report_data.py`
2. **文字分析生成**：`scripts/generate_task_report_narrative.py`
3. **HTML 渲染**：`scripts/render_task_html_report.py`

必须严格按这个顺序执行。

数据构建阶段是确定性的，必须先完成。
文字分析生成阶段可以调用 OpenAI 兼容接口，也可以落到兜底文案。
HTML 渲染阶段必须把图表数据和业务化文字一起反填到 `assets/task_report_template.html`。

## 问答策略

- 计数、排名、金额这类问题，优先用 Python 结果回答
- 模型主要用于业务化解释和高层总结，不用于原始计数
- 回答任务级问题时，优先带上任务编号和计算结果
- 能带证据字段时，尽量带交易时间、金额、交易对手、匹配用户
- 如果问题含糊且定位不到任务，就要求用户补充任务编号或任务标题

## 资源地图

- `references/board_manifest.json`：导出的任务索引
- `references/board_summary.json`：看板汇总指标
- `references/workflow.md`：简版执行流程
- `references/environment.md`：依赖和环境说明
- `references/reporting.md`：报告内容和图表建议
- `references/question_examples.md`：示例问题
- `references/task_report_prompt.md`：大模型文字分析提示词
- `assets/task_report_template.html`：单任务精美报告模板
- `assets/board_report_template.html`：看板概览模板
- `scripts/check_environment.py`：环境校验
- `scripts/query_task_index.py`：任务定位
- `scripts/build_task_report_data.py`：任务指标计算
- `scripts/generate_task_report_narrative.py`：业务化文字生成
- `scripts/render_task_html_report.py`：HTML 报告生成
- `scripts/answer_question.py`：轻量脚本问答入口

## 输出路径

- 任务分析 JSON：`output/task_reports/<task_id>/report_data.json`
- 任务文字分析 JSON：`output/task_reports/<task_id>/narrative.json`
- 最终 HTML 报告：`output/task_reports/<task_id>/<task_id>_审查分析报告.html`

## 约束

- 不要用看板汇总代替任务级 Excel 事实
- 不要未经检查就假设最终审查流水 Excel 一定存在
- 如果用了兜底文案，不要声称整份报告是模型生成的
- 不要编造缺失指标或系统未支持的异常数量
- 在新机器或新环境上，不要跳过环境校验
"""

    @staticmethod
    def _build_workflow_reference() -> str:
        return """# 工作流

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

这个包用于读取 `最终审查流水.xlsx`。

```bash
python -m pip install openpyxl
```

## 如果缺少 `requests`

这个包用于在文字分析阶段调用 OpenAI 兼容接口。

```bash
python -m pip install requests
```

## 如果缺少模型接口密钥

在做文字分析前，建议设置这些环境变量：

- `OPENAI_API_KEY`
- 可选：`OPENAI_API_BASE`
- 可选：`OPENAI_MODEL`

如果没有接口密钥，整条报告流水线仍然可以运行，但文字分析会退回到脚本兜底文案。
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

## 推荐生成逻辑

1. 用 Python 先算指标
2. 用模型生成业务化文字
3. 在 HTML 中渲染图表和表格

## 兜底行为

如果模型不可用，保留报告结构和图表，用兜底文案完成报告，不要让整条报告链路直接失败。
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
