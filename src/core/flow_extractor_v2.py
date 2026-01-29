# -*- coding: utf-8 -*-
"""
V2 Flow extractor with AI-only table classification and normalization.
"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import get_config
from ..parsers import PDFParser, ExcelParser, DocxParser
from ..parsers.base import FlowRecord, RawTable
from ..llm.flow_table_classifier import FlowTableClassifier
from ..llm.data_normalizer import FlowDataNormalizer
from .scanner import DocumentScanner
from .progress_manager import ProgressManager, ProgressStatus
from .checkpoint_manager import CheckpointManager
from .extraction_result import ExtractionResult

logger = logging.getLogger(__name__)


class FlowExtractorV2:
    """
    V2 Flow extractor:
    Stage 1 (serial): extract tables and classify flow tables; capture header attributes.
    Stage 2 (parallel): normalize flow rows into standardized records.
    """

    def __init__(self, config=None):
        self.config = config or get_config()
        self.scanner = DocumentScanner()

        self.pdf_parser = PDFParser(
            mineru_url=self.config.mineru_url,
            timeout=self.config.mineru_timeout
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

        self.progress = ProgressManager()
        self.checkpoints = CheckpointManager(self.config.config_dir / "checkpoints")
        self._cancel_requested = False
        self._lock = threading.Lock()

    def set_progress_callback(self, callback) -> None:
        self.progress.set_callback(callback)

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def extract_flows(
        self,
        document_folder: str,
        task_id: Optional[str] = None,
        batch_size: int = 20,
        confidence_threshold: Optional[int] = None,
        parallelism: Optional[int] = None
    ) -> ExtractionResult:
        self._cancel_requested = False
        threshold = confidence_threshold if confidence_threshold is not None else self.config.flow_confidence_threshold
        workers = parallelism if parallelism is not None else self.config.flow_parallelism

        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not self.table_classifier.is_available() or not self.data_normalizer.is_available():
            message = "未配置LLM API Key，无法进行AI流水提取"
            self.progress.report(message, status=ProgressStatus.FAILED)
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

        self.checkpoints.start_task(task_id, [p.name for p in documents])
        existing_states = {
            state.get("document_name"): state
            for state in self.checkpoints.list_document_states(task_id)
            if state.get("document_name")
        }
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

        stage2_doc_names: List[str] = []

        # Stage 1: serial classification
        logger.info("阶段1开始：逐文档表格识别与流水判定（串行）")
        processed_docs = 0
        for idx, doc_path in enumerate(documents):
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
            existing_state = existing_states.get(doc_path.name)
            if existing_state and existing_state.get("status") in ("stage1_done", "stage2_running", "completed"):
                stage2_doc_names.append(doc_path.name)
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
                stage2_doc_names.append(doc_path.name)
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
            return result
        logger.info("阶段2开始：流水行标准化（并行度=%s）", workers)
        flow_records = self._process_documents_stage2(
            stage2_doc_names, task_id, batch_size, workers, result, total_stage2_rows
        )
        result.flow_records.extend(flow_records)
        result.total_records = len(result.flow_records)

        if not self._cancel_requested:
            self.progress.report(f"提取完成: {result.total_records} 条流水", status=ProgressStatus.COMPLETED)
            logger.info("提取完成：%d 条流水，失败文档 %d 个", result.total_records, len(result.failed_documents))
            self._write_report(task_id, result)
            self.checkpoints.clear_task(task_id)

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
            "status": "stage1_done",
            "header_attributes": [],
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
            self.checkpoints.save_document_state(task_id, doc_path.name, state)
            return state, stats

        raw_tables = self._extract_raw_tables(doc_path, parser)
        logger.info("文档解析完成: %s，抽取到表格 %d 个", doc_path.name, len(raw_tables))
        stats["total_tables"] = len(raw_tables)
        state["total_tables"] = len(raw_tables)
        if not raw_tables:
            state["errors"].append("未抽取到任何表格")
            self.checkpoints.save_document_state(task_id, doc_path.name, state)
            return state, stats

        doc_header_attributes: Optional[List[str]] = None

        for table in raw_tables:
            if self._cancel_requested:
                break

            if not table.rows:
                logger.debug("表格为空，跳过: %s table#%s", doc_path.name, table.table_index)
                continue

            decision = self.table_classifier.analyze_table(table, doc_path.name)
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

            header_attributes = decision.get("header_attributes", [])
            header_row_index = int(decision.get("header_row_index", -1))
            data_start_row = int(decision.get("data_start_row", 0))

            if not header_attributes:
                col_count = len(table.rows[0]) if table.rows else 0
                header_attributes = [""] * col_count
            else:
                col_count = len(table.rows[0]) if table.rows else len(header_attributes)
                if len(header_attributes) < col_count:
                    header_attributes = header_attributes + [""] * (col_count - len(header_attributes))
                elif len(header_attributes) > col_count:
                    header_attributes = header_attributes[:col_count]

            if doc_header_attributes is None or not doc_header_attributes:
                if header_attributes:
                    doc_header_attributes = header_attributes
                    state["header_attributes"] = doc_header_attributes

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

            self.checkpoints.save_document_state(task_id, doc_path.name, state)

        if doc_header_attributes is None:
            state["status"] = "completed"
            self.checkpoints.save_document_state(task_id, doc_path.name, state)

        return state, stats

    def _process_documents_stage2(
        self,
        doc_names: List[str],
        task_id: str,
        batch_size: int,
        workers: int,
        result: ExtractionResult,
        total_rows: int
    ) -> List[FlowRecord]:
        if not doc_names:
            return []
        if self._cancel_requested:
            return []

        flow_records: List[FlowRecord] = []
        self._stage2_total_rows = max(0, int(total_rows))
        self._stage2_done_rows = 0

        def process_doc(doc_name: str) -> List[FlowRecord]:
            if self._cancel_requested:
                return []
            state = self.checkpoints.load_document_state(task_id, doc_name) or {}
            if state.get("status") == "completed" and state.get("records"):
                logger.info("阶段2读取缓存结果: %s (%d 条)", doc_name, len(state.get("records", [])))
                return [
                    FlowRecord(
                        source_file=item.get("source_file", doc_name),
                        original_row=int(item.get("original_row", 0) or 0),
                        transaction_time=item.get("transaction_time", "") or "",
                        counterparty_name=item.get("counterparty_name", "") or "",
                        counterparty_account=item.get("counterparty_account", "") or "",
                        amount=item.get("amount", "") or "",
                        summary=item.get("summary", "") or "",
                        transaction_type=item.get("transaction_type", "") or ""
                    )
                    for item in state.get("records", [])
                ]
            if not state.get("flow_tables"):
                logger.warning("阶段2无可处理流水表: %s", doc_name)
                return []
            header_attributes = state.get("header_attributes", []) or []
            rows_tables = state.get("flow_tables", [])
            if not header_attributes and rows_tables:
                first_rows = rows_tables[0].get("rows", [])
                if first_rows:
                    header_attributes = [""] * len(first_rows[0])

            doc_records: List[FlowRecord] = []
            processed_rows = 0
            total_rows = sum(len(t.get("rows", [])) for t in rows_tables)
            invalid_rows = 0
            normalized_rows = 0
            checkpoint_interval = max(1, int(self.config.flow_checkpoint_interval))
            logger.info("阶段2处理文档: %s (表格=%d, 行数=%d)", doc_name, len(rows_tables), total_rows)

            for table in rows_tables:
                if self._cancel_requested:
                    break
                data_start_row = int(table.get("data_start_row", 0))
                rows = table.get("rows", [])
                if not rows:
                    continue

                for i in range(0, len(rows), batch_size):
                    if self._cancel_requested:
                        break
                    batch_rows = rows[i:i + batch_size]
                    payload_rows = [
                        {"row_index": data_start_row + i + idx + 1, "cells": row}
                        for idx, row in enumerate(batch_rows)
                    ]
                    if self._cancel_requested:
                        break
                    normalized = self.data_normalizer.normalize_rows(
                        document_name=doc_name,
                        header_attributes=header_attributes,
                        rows=payload_rows,
                        source_file=doc_name
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
                        state["status"] = "stage2_running"
                        state["processed_rows"] = processed_rows
                        self.checkpoints.save_document_state(task_id, doc_name, state)

            state["status"] = "completed"
            state["normalized_records"] = len(doc_records)
            state["records"] = [r.to_dict() for r in doc_records]
            self.checkpoints.save_document_state(task_id, doc_name, state)
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
            for doc_name in doc_names:
                flow_records.extend(process_doc(doc_name))
            return flow_records

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_doc, name): name for name in doc_names}
            for future in as_completed(futures):
                try:
                    records = future.result()
                    if records:
                        flow_records.extend(records)
                except Exception as exc:
                    doc_name = futures[future]
                    logger.error("Stage2 处理文档失败 %s: %s", doc_name, exc)
                    with self._lock:
                        result.failed_documents.append(doc_name)
                        result.errors.append({
                            "document": doc_name,
                            "stage": "stage2",
                            "error": str(exc)
                        })

        return flow_records

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
            if file_path.suffix.lower() == ".pdf":
                parse_result = parser.parse(file_path)
                if not parse_result.success:
                    return []
                from ..parsers.html_parser import HTMLTableParser
                html_parser = HTMLTableParser()
                return html_parser.extract_raw_tables_from_html(parse_result.raw_text)
            if file_path.suffix.lower() in (".xlsx", ".xls"):
                return parser.extract_raw_tables(file_path)
            if file_path.suffix.lower() == ".docx":
                return parser.extract_raw_tables(file_path)
            return []
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
