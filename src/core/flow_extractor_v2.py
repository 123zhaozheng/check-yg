# -*- coding: utf-8 -*-
"""
V2 Flow extractor with AI-only table classification and normalization.
"""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_config
from ..parsers import PDFParser, ExcelParser, DocxParser
from ..parsers.base import FlowRecord, RawTable
from ..llm.flow_table_classifier import FlowTableClassifier
from ..llm.data_normalizer import FlowDataNormalizer
from ..llm.document_portrait import DocumentPortraitExtractor
from .scanner import DocumentScanner
from .progress_manager import ProgressManager, ProgressStatus
from .checkpoint_manager import CheckpointManager
from .extraction_result import ExtractionResult

logger = logging.getLogger(__name__)


class FlowExtractorV2:
    """
    V2 Flow extractor:
    Stage 1 (serial): extract tables, classify flow tables, and extract document portrait (with header mapping).
    Stage 2 (parallel): normalize flow rows into standardized records using portrait column mapping.
    """

    def __init__(self, config=None):
        self.config = config or get_config()
        self.scanner = DocumentScanner()

        self.pdf_parser = PDFParser(
            mineru_url=self.config.mineru_url,
            timeout=self.config.mineru_timeout,
            mineru_mode=getattr(self.config, "mineru_mode", "local"),
            mineru_public_url=getattr(
                self.config,
                "mineru_public_url",
                "https://mineru.net/api/v1/agent",
            ),
            mineru_public_api_key=getattr(self.config, "mineru_public_api_key", ""),
        )
        self.excel_parser = ExcelParser()
        self.docx_parser = DocxParser()

        self.table_classifier = FlowTableClassifier(
            api_url=self.config.llm_url,
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
            timeout=self.config.llm_timeout,
            preview_rows=self.config.flow_preview_rows
        )
        self.data_normalizer = FlowDataNormalizer(
            api_url=self.config.llm_url,
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
            timeout=self.config.llm_timeout
        )
        self.portrait_extractor = DocumentPortraitExtractor(
            api_url=self.config.llm_url,
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
            timeout=self.config.llm_timeout,
        )

        self.progress = ProgressManager()
        self.checkpoints = CheckpointManager(self.config.config_dir / "checkpoints")
        self._cancel_requested = False
        self._pause_requested = False
        self._pause_condition = threading.Condition()
        self._lock = threading.Lock()

    def set_progress_callback(self, callback) -> None:
        self.progress.set_callback(callback)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        with self._pause_condition:
            self._pause_condition.notify_all()

    def request_pause(self, pause: bool) -> None:
        """请求暂停或继续提取。"""
        with self._pause_condition:
            self._pause_requested = pause
            if not pause:
                self._pause_condition.notify_all()

    def _check_pause(self) -> None:
        """检查并执行暂停。"""
        with self._pause_condition:
            while self._pause_requested and not self._cancel_requested:
                self._pause_condition.wait()

    def extract_flows(
        self,
        document_folder: str,
        task_id: Optional[str] = None,
        batch_size: int = 20,
        confidence_threshold: Optional[int] = None,
        parallelism: Optional[int] = None
    ) -> ExtractionResult:
        self._cancel_requested = False
        self._pause_requested = False
        threshold = confidence_threshold if confidence_threshold is not None else self.config.flow_confidence_threshold
        workers = parallelism if parallelism is not None else self.config.flow_parallelism

        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not self.table_classifier.is_available() or not self.data_normalizer.is_available():
            message = "未配置LLM API Key，无法进行AI流水提取"
            self.progress.report(message, status=ProgressStatus.FAILED)
            self.checkpoints.start_task(
                task_id,
                documents=[],
                title=task_id,
                document_folder=document_folder,
            )
            self.checkpoints.update_task_status(task_id, "failed")
            return ExtractionResult(
                task_id=task_id,
                task_time=datetime.now().isoformat(),
                document_folder=document_folder,
                total_documents=0,
                processed_documents=0,
                total_tables=0,
                flow_tables=0,
                total_records=0,
                failed_documents=[],
                errors=[{"stage": "init", "error": message}]
            )

        logger.info("开始扫描文档目录: %s", document_folder)
        self.progress.report(f"正在扫描文档目录: {document_folder}", status=ProgressStatus.RUNNING)
        documents = self.scanner.scan_directory(document_folder)
        logger.info("扫描完成，共发现 %d 个文档", len(documents))
        self._stage1_total_docs = len(documents)
        self.progress.report(
            f"阶段1/2 已发现 {len(documents)} 个文档",
            0,
            max(1, len(documents))
        )

        self.checkpoints.start_task(
            task_id,
            [str(p) for p in documents],
            title=task_id,
            document_folder=document_folder,
        )
        self.checkpoints.update_task_status(task_id, "extracting")
        existing_states: Dict[str, Dict] = {}
        for state in self.checkpoints.list_document_states(task_id):
            document_path = str(state.get("document_path", "") or "").strip()
            document_name = str(state.get("document_name", "") or "").strip()
            if document_path:
                existing_states[document_path] = state
            elif document_name and document_name not in existing_states:
                existing_states[document_name] = state
        total_stage2_rows = 0

        result = ExtractionResult(
            task_id=task_id,
            task_time=datetime.now().isoformat(),
            document_folder=document_folder,
            total_documents=len(documents),
            processed_documents=0,
            total_tables=0,
            flow_tables=0,
            total_records=0
        )

        stage2_doc_paths: List[str] = []

        # Stage 1: serial classification
        logger.info("阶段1开始：逐文档表格识别与流水判定（串行）")
        processed_docs = 0
        for idx, doc_path in enumerate(documents):
            self._check_pause()
            if self._cancel_requested:
                self.progress.report("提取已取消", status=ProgressStatus.CANCELED)
                break

            total_units = self._stage1_total_docs + total_stage2_rows
            self.progress.report(
                f"阶段1/2 正在处理: {doc_path.name}",
                processed_docs,
                max(1, total_units)
            )
            logger.info("阶段1处理文档: %s (%d/%d)", doc_path.name, idx + 1, len(documents))
            existing_state = existing_states.get(str(doc_path)) or existing_states.get(doc_path.name)
            if existing_state and existing_state.get("status") in (
                "stage1_done",
                "stage2_running",
                "normalizing",
                "completed",
            ):
                stage2_doc_paths.append(str(doc_path))
                result.total_tables += int(existing_state.get("total_tables", 0) or 0)
                result.flow_tables += int(existing_state.get("flow_tables_count", 0) or 0)
                result.processed_documents += 1
                total_stage2_rows += int(existing_state.get("total_flow_rows", 0) or 0)
                processed_docs += 1
                total_units = self._stage1_total_docs + total_stage2_rows
                self.progress.report(
                    f"阶段1/2 已处理: {doc_path.name}",
                    processed_docs,
                    max(1, total_units)
                )
                logger.info(
                    "阶段1跳过已处理文档: %s (total_tables=%s, flow_tables=%s, flow_rows=%s)",
                    doc_path.name,
                    existing_state.get("total_tables", 0),
                    existing_state.get("flow_tables_count", 0),
                    existing_state.get("total_flow_rows", 0)
                )
                for err in existing_state.get("errors", []):
                    result.errors.append({
                        "document": doc_path.name,
                        "stage": "resume",
                        "error": err
                    })
                continue
            try:
                doc_state, stats = self._process_document_stage1(
                    doc_path, task_id, threshold
                )
                stage2_doc_paths.append(str(doc_path))
                result.total_tables += stats["total_tables"]
                result.flow_tables += stats["flow_tables"]
                result.processed_documents += 1
                total_stage2_rows += int(doc_state.get("total_flow_rows", 0) or 0)
                processed_docs += 1
                total_units = self._stage1_total_docs + total_stage2_rows
                self.progress.report(
                    f"阶段1/2 已处理: {doc_path.name}",
                    processed_docs,
                    max(1, total_units)
                )
                logger.info(
                    "阶段1完成文档: %s (total_tables=%d, flow_tables=%d, flow_rows=%d)",
                    doc_path.name,
                    stats["total_tables"],
                    stats["flow_tables"],
                    int(doc_state.get("total_flow_rows", 0) or 0)
                )
                for err in doc_state.get("errors", []):
                    result.errors.append({
                        "document": doc_path.name,
                        "stage": "stage1",
                        "error": err
                    })
            except Exception as exc:
                logger.error("Stage1 处理文档失败 %s: %s", doc_path.name, exc)
                result.failed_documents.append(doc_path.name)
                result.errors.append({
                    "document": doc_path.name,
                    "stage": "stage1",
                    "error": str(exc)
                })

        # Stage 2: parallel normalization
        if self._cancel_requested:
            logger.info("提取已取消，跳过阶段2")
            self.checkpoints.update_task_status(task_id, "canceled")
            return result
        self.checkpoints.update_task_status(task_id, "normalizing")
        logger.info("阶段2开始：流水行标准化（并行度=%s）", workers)
        flow_records = self._process_documents_stage2(
            stage2_doc_paths, task_id, batch_size, workers, result, total_stage2_rows
        )
        result.flow_records.extend(flow_records)
        result.total_records = len(result.flow_records)

        if self._cancel_requested:
            self.checkpoints.update_task_status(task_id, "canceled")
        else:
            final_status = "failed" if result.failed_documents else "completed"
            self.checkpoints.update_task_status(task_id, final_status)
            progress_status = ProgressStatus.FAILED if final_status == "failed" else ProgressStatus.COMPLETED
            self.progress.report(f"提取完成: {result.total_records} 条流水", status=progress_status)
            logger.info("提取完成：%d 条流水，失败文档 %d 个", result.total_records, len(result.failed_documents))
            self._write_report(task_id, result)
            if final_status != "completed":
                logger.info("任务含失败文档，保留断点以便排查: %s", task_id)
            elif self.config.flow_keep_checkpoint_on_success:
                logger.info("配置要求保留文档断点，任务 checkpoint 未清理: %s", task_id)
            else:
                self.checkpoints.clear_document_states(task_id)
                logger.info("任务已完成，已清理文档断点但保留任务历史: %s", task_id)

        return result

    def _process_document_stage1(
        self,
        doc_path: Path,
        task_id: str,
        confidence_threshold: int
    ) -> Tuple[Dict, Dict[str, int]]:
        stats = {"total_tables": 0, "flow_tables": 0}
        state: Dict = {
            "document_name": doc_path.name,
            "document_path": str(doc_path),
            "status": "extracting",
            "flow_tables": [],
            "total_tables": 0,
            "flow_tables_count": 0,
            "total_flow_rows": 0,
            "errors": []
        }

        parser = self._get_parser_for_file(doc_path)
        if not parser:
            state["status"] = "failed"
            state["errors"].append("无解析器")
            self.checkpoints.save_document_state(
                task_id, doc_path.name, state, document_path=str(doc_path)
            )
            return state, stats

        raw_tables = self._extract_raw_tables(doc_path, parser)
        logger.info("文档解析完成: %s，抽取到表格 %d 个", doc_path.name, len(raw_tables))
        stats["total_tables"] = len(raw_tables)
        state["total_tables"] = len(raw_tables)
        if not raw_tables:
            state["status"] = "completed"
            state["errors"].append("未抽取到任何表格")
            self.checkpoints.save_document_state(
                task_id, doc_path.name, state, document_path=str(doc_path)
            )
            return state, stats

        # 提取非表格文本，用于文档画像
        non_table_context = ""
        if hasattr(parser, 'extract_non_table_context'):
            try:
                non_table_context = parser.extract_non_table_context(
                    doc_path, max_chars=self.config.flow_portrait_max_chars
                )
            except Exception as exc:
                logger.warning("提取non_table_context失败 %s: %s", doc_path.name, exc)

        # Build content preview from raw tables for portrait extraction
        content_preview = ""
        if raw_tables:
            preview_lines = []
            for table in raw_tables[:3]:
                preview = table.get_preview(self.config.flow_portrait_lines)
                if preview:
                    preview_lines.append(preview)
            content_preview = "\n\n".join(preview_lines)

        # 画像提取与分类并行：先提交画像任务，分类循环完成后取结果
        portrait_future = None
        portrait_executor = None
        if non_table_context and self.portrait_extractor.is_available():
            logger.info("开始提取文档画像: %s (非表格文本长度=%d)", doc_path.name, len(non_table_context))
            portrait_executor = ThreadPoolExecutor(max_workers=1)
            portrait_future = portrait_executor.submit(
                self.portrait_extractor.extract_portrait,
                doc_path.name,
                non_table_context,
                content_preview,
            )
        elif not non_table_context:
            logger.info("文档无非表格文本，跳过画像提取: %s", doc_path.name)

        for table in raw_tables:
            self._check_pause()
            if self._cancel_requested:
                break

            if not table.rows:
                logger.debug("表格为空，跳过: %s table#%s", doc_path.name, table.table_index)
                continue

            decision = self.table_classifier.analyze_table(
                table, doc_path.name, content_preview=non_table_context
            )
            if not decision:
                state["errors"].append(
                    f"AI表格判断失败: table#{table.table_index}"
                )
                logger.warning("AI表格判断失败: %s table#%s", doc_path.name, table.table_index)
                continue

            is_flow = bool(decision.get("is_flow_table"))
            confidence = int(decision.get("confidence", 0))
            logger.debug(
                "表格判定: %s table#%s is_flow=%s confidence=%d threshold=%d",
                doc_path.name, table.table_index, is_flow, confidence, confidence_threshold
            )
            if not is_flow or confidence < confidence_threshold:
                logger.debug(
                    "表格未达标跳过: %s table#%s (is_flow=%s confidence=%d)",
                    doc_path.name, table.table_index, is_flow, confidence
                )
                continue

            stats["flow_tables"] += 1
            state["flow_tables_count"] += 1

            header_row_index = int(decision.get("header_row_index", -1))
            data_start_row = int(decision.get("data_start_row", 0))

            if header_row_index < 0:
                data_start_row = max(0, data_start_row)
            else:
                data_start_row = max(header_row_index + 1, data_start_row)
            data_start_row = min(data_start_row, len(table.rows))

            table_rows = table.rows[data_start_row:]
            state["flow_tables"].append({
                "table_index": table.table_index,
                "header_row_index": header_row_index,
                "data_start_row": data_start_row,
                "rows": table_rows
            })
            state["total_flow_rows"] += len(table_rows)

            self.checkpoints.save_document_state(
                task_id, doc_path.name, state, document_path=str(doc_path)
            )

        # 等待画像提取结果
        document_portrait = None
        if portrait_future is not None:
            try:
                document_portrait = portrait_future.result(timeout=self.config.llm_timeout)
                if document_portrait is not None:
                    logger.info("文档画像提取完成: %s 画像=%s", doc_path.name, json.dumps(document_portrait, ensure_ascii=False))
            except Exception as exc:
                logger.warning("画像提取超时或失败 %s: %s", doc_path.name, exc)
        if portrait_executor is not None:
            portrait_executor.shutdown(wait=False)

        if document_portrait is None:
            logger.warning("文档画像提取失败，降级到文件名推断: %s", doc_path.name)
            document_portrait = FlowDataNormalizer._infer_document_context(doc_path.name)
        state["document_portrait"] = document_portrait
        state["non_table_context"] = non_table_context

        if state["flow_tables"]:
            state["status"] = "normalizing"
        else:
            state["status"] = "completed"
        self.checkpoints.save_document_state(
            task_id, doc_path.name, state, document_path=str(doc_path)
        )

        return state, stats

    def _process_documents_stage2(
        self,
        doc_paths: List[str],
        task_id: str,
        batch_size: int,
        workers: int,
        result: ExtractionResult,
        total_rows: int
    ) -> List[FlowRecord]:
        if not doc_paths:
            return []
        if self._cancel_requested:
            return []

        flow_records: List[FlowRecord] = []
        self._stage2_total_rows = max(0, int(total_rows))
        self._stage2_done_rows = self._get_stage2_done_rows(task_id, doc_paths)

        def process_doc(document_path: str) -> List[FlowRecord]:
            if self._cancel_requested:
                return []
            doc_path = Path(document_path)
            doc_name = doc_path.name
            state = self.checkpoints.load_document_state(
                task_id,
                doc_name,
                document_path=document_path
            ) or {}
            if state.get("status") == "completed" and state.get("records"):
                logger.info("阶段2读取缓存结果: %s (%d 条)", doc_name, len(state.get("records", [])))
                return self._deserialize_records(state.get("records", []), doc_name)
            if not state.get("flow_tables"):
                logger.warning("阶段2无可处理流水表: %s", doc_name)
                return []
            header_attributes = state.get("header_attributes", []) or []
            rows_tables = state.get("flow_tables", [])

            document_portrait = state.get("document_portrait")
            if document_portrait is None:
                document_portrait = FlowDataNormalizer._infer_document_context(doc_name)

            # 优先从画像取 header_attributes（画像同时提供 column_mapping）
            portrait_header = (document_portrait or {}).get("header_attributes")
            if portrait_header:
                header_attributes = portrait_header
            elif not header_attributes and rows_tables:
                # 降级：画像无 header_attributes 且 state 也无，从行数据推断列数
                first_rows = rows_tables[0].get("rows", [])
                if first_rows:
                    header_attributes = [""] * len(first_rows[0])
                    logger.info("画像无header_attributes，降级填充空表头: %s 列数=%d", doc_name, len(header_attributes))

            # 向后兼容：旧画像不含 header_attributes，从 state/降级逻辑注入
            if header_attributes and document_portrait is not None and "header_attributes" not in document_portrait:
                document_portrait = dict(document_portrait)
                document_portrait["header_attributes"] = header_attributes

            # 记录 column_mapping 是否可用
            column_mapping = (document_portrait or {}).get("column_mapping")
            if not column_mapping:
                logger.info("画像无column_mapping，标准化器将尽力自行映射: %s", doc_name)

            total_doc_rows = sum(len(t.get("rows", [])) for t in rows_tables)
            resume_offset = int(state.get("processed_rows", 0) or 0)
            resume_offset = max(0, min(total_doc_rows, resume_offset))
            doc_records: List[FlowRecord] = self._deserialize_records(state.get("records", []), doc_name)
            if resume_offset > 0 and not doc_records:
                logger.warning("文档 %s 存在 processed_rows 但无缓存记录，将从头重新处理", doc_name)
                resume_offset = 0

            processed_rows = resume_offset
            invalid_rows = 0
            normalized_rows = 0
            checkpoint_interval = max(1, int(self.config.flow_checkpoint_interval))
            logger.info(
                "阶段2处理文档: %s (表格=%d, 行数=%d, 续跑偏移=%d)",
                doc_name, len(rows_tables), total_doc_rows, resume_offset
            )

            row_cursor = 0

            for table in rows_tables:
                if self._cancel_requested:
                    break
                data_start_row = int(table.get("data_start_row", 0))
                rows = table.get("rows", [])
                if not rows:
                    continue
                if row_cursor + len(rows) <= resume_offset:
                    row_cursor += len(rows)
                    continue

                table_start = max(0, resume_offset - row_cursor)
                for i in range(table_start, len(rows), batch_size):
                    self._check_pause()
                    if self._cancel_requested:
                        break
                    batch_rows = rows[i:i + batch_size]
                    if not batch_rows:
                        continue
                    payload_rows = [
                        {"row_index": data_start_row + i + idx + 1, "cells": row}
                        for idx, row in enumerate(batch_rows)
                    ]
                    if self._cancel_requested:
                        break
                    normalized = self.data_normalizer.normalize_rows(
                        document_name=doc_name,
                        rows=payload_rows,
                        source_file=doc_name,
                        document_portrait=document_portrait,
                    )
                    if normalized is None:
                        state.setdefault("errors", []).append(
                            f"AI标准化失败: {doc_name} batch {i}-{i + len(batch_rows)}"
                        )
                        logger.warning(
                            "AI标准化失败: %s batch %d-%d", doc_name, i, i + len(batch_rows)
                        )
                    else:
                        normalized_rows += len(normalized)
                        # Post-processing: code-based transaction_type inference
                        amount_sign_rule = (document_portrait or {}).get("amount_sign_rule", "unknown")
                        for item in normalized:
                            if item.get("is_valid", True):
                                raw_amount = str(item.get("raw_amount", "") or "")
                                inferred_type = FlowExtractorV2._infer_transaction_type(
                                    raw_amount, amount_sign_rule, document_portrait
                                )
                                if inferred_type:
                                    if item.get("transaction_type") != inferred_type:
                                        logger.info(
                                            "代码修正收支类型: %s raw_amount=%s LLM=%s → 代码=%s (rule=%s)",
                                            doc_name, raw_amount, item.get("transaction_type"), inferred_type, amount_sign_rule
                                        )
                                        item["transaction_type"] = inferred_type
                        for item in normalized:
                            if not item.get("is_valid", True):
                                invalid_rows += 1
                                continue
                            doc_records.append(FlowRecord(
                                source_file=item.get("source_file", doc_name),
                                original_row=int(item.get("row_index", 0) or 0),
                                transaction_time=item.get("transaction_time", "") or "",
                                counterparty_name=item.get("counterparty_name", "") or "",
                                counterparty_account=item.get("counterparty_account", "") or "",
                                amount=item.get("amount", "") or "",
                                summary=item.get("summary", "") or "",
                                transaction_type=item.get("transaction_type", "") or ""
                            ))
                    processed_rows += len(batch_rows)
                    self._report_stage2_progress(doc_name, len(batch_rows))
                    if processed_rows % checkpoint_interval == 0:
                        state["status"] = "normalizing"
                        state["processed_rows"] = processed_rows
                        state["normalized_records"] = len(doc_records)
                        state["records"] = [r.to_dict() for r in doc_records]
                        self.checkpoints.save_document_state(
                            task_id,
                            doc_name,
                            state,
                            document_path=document_path
                        )
                row_cursor += len(rows)

            if self._cancel_requested:
                state["status"] = "canceled"
            else:
                state["status"] = "completed"
            state["processed_rows"] = processed_rows
            state["normalized_records"] = len(doc_records)
            state["records"] = [r.to_dict() for r in doc_records]
            self.checkpoints.save_document_state(
                task_id,
                doc_name,
                state,
                document_path=document_path
            )
            if self._cancel_requested:
                logger.info(
                    "阶段2已取消并保存文档状态: %s (已处理行=%d, 产出记录=%d)",
                    doc_name, processed_rows, len(doc_records)
                )
            else:
                logger.info(
                    "阶段2完成文档: %s (标准化=%d, 无效行=%d, 产出记录=%d)",
                    doc_name, normalized_rows, invalid_rows, len(doc_records)
                )
            if state.get("errors"):
                with self._lock:
                    for err in state.get("errors", []):
                        result.errors.append({
                            "document": doc_name,
                            "stage": "stage2",
                            "error": err
                        })
            return doc_records

        if workers <= 1:
            for document_path in doc_paths:
                flow_records.extend(process_doc(document_path))
            return flow_records

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_doc, path): path for path in doc_paths}
            for future in as_completed(futures):
                try:
                    records = future.result()
                    if records:
                        flow_records.extend(records)
                except Exception as exc:
                    document_path = futures[future]
                    doc_name = Path(document_path).name
                    logger.error("Stage2 处理文档失败 %s: %s", doc_name, exc)
                    with self._lock:
                        result.failed_documents.append(doc_name)
                        result.errors.append({
                            "document": doc_name,
                            "stage": "stage2",
                            "error": str(exc)
                        })

        return flow_records

    @staticmethod
    def _deserialize_records(items: List[Dict], doc_name: str) -> List[FlowRecord]:
        records: List[FlowRecord] = []
        for item in items or []:
            records.append(FlowRecord(
                source_file=item.get("source_file", doc_name),
                original_row=int(item.get("original_row", 0) or 0),
                transaction_time=item.get("transaction_time", "") or "",
                counterparty_name=item.get("counterparty_name", "") or "",
                counterparty_account=item.get("counterparty_account", "") or "",
                amount=item.get("amount", "") or "",
                summary=item.get("summary", "") or "",
                transaction_type=item.get("transaction_type", "") or ""
            ))
        return records

    @staticmethod
    def _infer_transaction_type(
        raw_amount: str,
        amount_sign_rule: str,
        portrait: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Infer transaction_type from raw_amount sign and amount_sign_rule.
        Returns "收入" or "支出", or None if cannot determine.
        """
        if not raw_amount:
            return None

        # Credit card mode takes highest priority
        if portrait and portrait.get("account_type") == "credit_card":
            # For credit cards, we still rely on LLM judgment (semantic-based)
            # because credit card sign conventions vary and are counter-intuitive
            return None

        raw = str(raw_amount).strip()
        has_negative = raw.startswith("-")

        if amount_sign_rule == "pos_income":
            return "支出" if has_negative else "收入"
        elif amount_sign_rule == "pos_expense":
            return "收入" if has_negative else "支出"
        elif amount_sign_rule == "split_cols":
            return None  # LLM should handle this correctly
        elif amount_sign_rule == "no_sign":
            return None  # Must rely on LLM/summary
        elif amount_sign_rule == "unknown":
            # Fallback: if has sign, use it (assume pos_income as default for bank statements)
            if has_negative:
                return "支出"
            elif raw.startswith("+") or not has_negative:
                # Has explicit positive or no sign - uncertain
                return None
            return None
        return None

    def _get_stage2_done_rows(self, task_id: str, doc_paths: List[str]) -> int:
        done_rows = 0
        for document_path in doc_paths:
            doc_name = Path(document_path).name
            state = self.checkpoints.load_document_state(
                task_id,
                doc_name,
                document_path=document_path
            ) or {}
            status = state.get("status")
            if status == "completed":
                done_rows += int(state.get("total_flow_rows", 0) or 0)
                continue
            done_rows += int(state.get("processed_rows", 0) or 0)
        return max(0, done_rows)

    def _report_stage2_progress(self, doc_name: str, batch_rows: int) -> None:
        with self._lock:
            self._stage2_done_rows += batch_rows
            done = self._stage2_done_rows
            total = self._stage2_total_rows
            total_units = self._stage1_total_docs + total
            current_units = self._stage1_total_docs + done
            message = f"阶段2/2 正在标准化: {doc_name}"
            if total > 0:
                message = f"{message} ({done}/{total})"
            self.progress.report(message, current_units, max(1, total_units))

    def _get_parser_for_file(self, file_path: Path):
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            return self.pdf_parser
        if ext == ".docx":
            return self.docx_parser
        if ext in (".xlsx", ".xls"):
            return self.excel_parser
        return None

    def _extract_raw_tables(self, file_path: Path, parser) -> List[RawTable]:
        try:
            return parser.extract_raw_tables(file_path)
        except Exception as exc:
            logger.error("提取原始表格失败 %s: %s", file_path.name, exc)
            return []

    def _write_report(self, task_id: str, result: ExtractionResult) -> None:
        try:
            report_dir = self.config.reports_folder
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"extract_{task_id}.json"
            with open(report_path, "w", encoding="utf-8") as f:
                import json
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to write extraction report: %s", exc)

    def _load_existing_report_records(self, task_id: str) -> List[FlowRecord]:
        """从已有的提取报告文件中读取流水记录（用于追加合并）。"""
        report_path = self.config.reports_folder / f"extract_{task_id}.json"
        if not report_path.exists():
            return []
        try:
            import json as _json
            with open(report_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            records_data = data.get("flow_records", []) or []
            return self._deserialize_records(records_data, "")
        except Exception as exc:
            logger.warning("读取已有报告失败: %s", exc)
            return []

    def extract_flows_append(
        self,
        task_id: str,
        new_folder: str,
        batch_size: int = 20,
        confidence_threshold: Optional[int] = None,
        parallelism: Optional[int] = None
    ) -> ExtractionResult:
        """追加提取：扫描新文件夹，仅处理新增文档，结果合并写入报告。"""
        self._cancel_requested = False
        self._pause_requested = False
        threshold = confidence_threshold if confidence_threshold is not None else self.config.flow_confidence_threshold
        workers = parallelism if parallelism is not None else self.config.flow_parallelism

        if not self.table_classifier.is_available() or not self.data_normalizer.is_available():
            message = "未配置LLM API Key，无法进行AI流水提取"
            self.progress.report(message, status=ProgressStatus.FAILED)
            return ExtractionResult(
                task_id=task_id,
                task_time=datetime.now().isoformat(),
                document_folder=new_folder,
                total_documents=0,
                processed_documents=0,
                total_tables=0,
                flow_tables=0,
                total_records=0,
                failed_documents=[],
                errors=[{"stage": "init", "error": message}]
            )

        # Scan new folder
        logger.info("追加扫描文档目录: %s", new_folder)
        self.progress.report(f"正在扫描文档目录: {new_folder}", status=ProgressStatus.RUNNING)
        all_new_documents = self.scanner.scan_directory(new_folder)

        # Get existing documents from task metadata for dedup
        task_meta = self.checkpoints.load_task(task_id) or {}
        existing_docs = set(str(p) for p in (task_meta.get("documents", []) or []))

        # Filter: only truly new documents
        new_documents = [p for p in all_new_documents if str(p) not in existing_docs]

        if not new_documents:
            logger.info("追加扫描完成，未发现新文档")
            self.progress.report("该目录下未找到可处理的文档", status=ProgressStatus.COMPLETED)
            return ExtractionResult(
                task_id=task_id,
                task_time=datetime.now().isoformat(),
                document_folder=new_folder,
                total_documents=0,
                processed_documents=0,
                total_tables=0,
                flow_tables=0,
                total_records=0,
                failed_documents=[],
                errors=[]
            )

        logger.info("追加扫描完成，发现 %d 个新文档", len(new_documents))
        self._stage1_total_docs = len(new_documents)

        # Read existing report records before processing (for final merge)
        existing_report_records = self._load_existing_report_records(task_id)
        self.progress.report(
            f"阶段1/2 已发现 {len(new_documents)} 个新文档",
            0,
            max(1, len(new_documents))
        )

        # Append folder and documents to task metadata
        self.checkpoints.append_documents(
            task_id, new_folder, [str(p) for p in new_documents]
        )

        result = ExtractionResult(
            task_id=task_id,
            task_time=datetime.now().isoformat(),
            document_folder=new_folder,
            total_documents=len(new_documents),
            processed_documents=0,
            total_tables=0,
            flow_tables=0,
            total_records=0
        )

        stage2_doc_paths: List[str] = []
        existing_states: Dict[str, Dict] = {}
        for state in self.checkpoints.list_document_states(task_id):
            document_path = str(state.get("document_path", "") or "").strip()
            document_name = str(state.get("document_name", "") or "").strip()
            if document_path:
                existing_states[document_path] = state
            elif document_name and document_name not in existing_states:
                existing_states[document_name] = state

        total_stage2_rows = 0

        # Stage 1: serial classification (new documents only)
        logger.info("追加阶段1开始：逐文档表格识别与流水判定")
        processed_docs = 0
        for idx, doc_path in enumerate(new_documents):
            self._check_pause()
            if self._cancel_requested:
                self.progress.report("提取已取消", status=ProgressStatus.CANCELED)
                break

            total_units = self._stage1_total_docs + total_stage2_rows
            self.progress.report(
                f"阶段1/2 正在处理: {doc_path.name}",
                processed_docs,
                max(1, total_units)
            )
            logger.info("追加阶段1处理文档: %s (%d/%d)", doc_path.name, idx + 1, len(new_documents))
            existing_state = existing_states.get(str(doc_path)) or existing_states.get(doc_path.name)
            if existing_state and existing_state.get("status") in (
                "stage1_done",
                "stage2_running",
                "normalizing",
                "completed",
            ):
                stage2_doc_paths.append(str(doc_path))
                result.total_tables += int(existing_state.get("total_tables", 0) or 0)
                result.flow_tables += int(existing_state.get("flow_tables_count", 0) or 0)
                result.processed_documents += 1
                total_stage2_rows += int(existing_state.get("total_flow_rows", 0) or 0)
                processed_docs += 1
                total_units = self._stage1_total_docs + total_stage2_rows
                self.progress.report(
                    f"阶段1/2 已处理: {doc_path.name}",
                    processed_docs,
                    max(1, total_units)
                )
                continue
            try:
                doc_state, stats = self._process_document_stage1(
                    doc_path, task_id, threshold
                )
                stage2_doc_paths.append(str(doc_path))
                result.total_tables += stats["total_tables"]
                result.flow_tables += stats["flow_tables"]
                result.processed_documents += 1
                total_stage2_rows += int(doc_state.get("total_flow_rows", 0) or 0)
                processed_docs += 1
                total_units = self._stage1_total_docs + total_stage2_rows
                self.progress.report(
                    f"阶段1/2 已处理: {doc_path.name}",
                    processed_docs,
                    max(1, total_units)
                )
                logger.info(
                    "追加阶段1完成文档: %s (total_tables=%d, flow_tables=%d, flow_rows=%d)",
                    doc_path.name,
                    stats["total_tables"],
                    stats["flow_tables"],
                    int(doc_state.get("total_flow_rows", 0) or 0)
                )
                for err in doc_state.get("errors", []):
                    result.errors.append({
                        "document": doc_path.name,
                        "stage": "stage1",
                        "error": err
                    })
            except Exception as exc:
                logger.error("追加Stage1 处理文档失败 %s: %s", doc_path.name, exc)
                result.failed_documents.append(doc_path.name)
                result.errors.append({
                    "document": doc_path.name,
                    "stage": "stage1",
                    "error": str(exc)
                })

        # Stage 2: parallel normalization
        if self._cancel_requested:
            logger.info("追加提取已取消，跳过阶段2")
            self.checkpoints.update_task_status(task_id, "canceled")
            return result

        self.checkpoints.update_task_status(task_id, "normalizing")
        logger.info("追加阶段2开始：流水行标准化（并行度=%s）", workers)
        flow_records = self._process_documents_stage2(
            stage2_doc_paths, task_id, batch_size, workers, result, total_stage2_rows
        )
        result.flow_records.extend(flow_records)

        if self._cancel_requested:
            self.checkpoints.update_task_status(task_id, "canceled")
        else:
            # Combine existing report records (old) + new records from this append run
            all_records = existing_report_records + result.flow_records
            result.flow_records = all_records
            result.total_records = len(all_records)

            final_status = "failed" if result.failed_documents else "completed"
            self.checkpoints.update_task_status(task_id, final_status)
            progress_status = ProgressStatus.FAILED if final_status == "failed" else ProgressStatus.COMPLETED
            self.progress.report(f"追加提取完成: {result.total_records} 条流水", status=progress_status)
            logger.info("追加提取完成：%d 条流水，失败文档 %d 个", result.total_records, len(result.failed_documents))
            self._write_report(task_id, result)
            if final_status != "completed":
                logger.info("任务含失败文档，保留断点以便排查: %s", task_id)
            elif self.config.flow_keep_checkpoint_on_success:
                logger.info("配置要求保留文档断点，任务 checkpoint 未清理: %s", task_id)
            else:
                self.checkpoints.clear_document_states(task_id)
                logger.info("任务已完成，已清理文档断点但保留任务历史: %s", task_id)

        return result
