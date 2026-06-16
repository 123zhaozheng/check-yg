# -*- coding: utf-8 -*-
"""Main extraction pipeline orchestrator."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import settings
from ...llm import DocumentPortraitExtractor, FlowDataNormalizer, FlowTableClassifier
from ...parsers import DocxParser, ExcelParser, PDFParser
from ...parsers.base import FlowRecord, RawTable
from .checkpoint import CheckpointManager
from .progress import ProgressReporter
from .scanner import DocumentScanner

logger = logging.getLogger(__name__)


class ExtractionResult:
    """Result of extraction pipeline."""

    def __init__(self, task_id: str, document_folder: str = ""):
        self.task_id = task_id
        self.task_time = datetime.now().isoformat()
        self.document_folder = document_folder
        self.total_documents = 0
        self.processed_documents = 0
        self.total_tables = 0
        self.flow_tables = 0
        self.total_records = 0
        self.failed_documents: List[str] = []
        self.flow_records: List[FlowRecord] = []
        self.errors: List[Dict[str, Any]] = []
        self.per_document_stats: Dict[str, Dict[str, Any]] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_time": self.task_time,
            "document_folder": self.document_folder,
            "total_documents": self.total_documents,
            "processed_documents": self.processed_documents,
            "total_tables": self.total_tables,
            "flow_tables": self.flow_tables,
            "total_records": self.total_records,
            "failed_documents": self.failed_documents,
            "flow_records": [r.to_dict() for r in self.flow_records],
            "errors": self.errors,
            "per_document_stats": self.per_document_stats,
        }


class FlowExtractor:
    """Async flow extraction pipeline."""

    def __init__(self):
        self.scanner = DocumentScanner()
        self.checkpoint_manager = CheckpointManager()
        self.progress_reporter = ProgressReporter()

        # Initialize parsers
        self.pdf_parser = PDFParser()
        self.excel_parser = ExcelParser()
        self.docx_parser = DocxParser()

        # Initialize LLM components
        self.classifier = FlowTableClassifier(
            api_url=settings.LLM_API_ENDPOINT,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )
        self.normalizer = FlowDataNormalizer(
            api_url=settings.LLM_API_ENDPOINT,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )
        self.portrait_extractor = DocumentPortraitExtractor(
            api_url=settings.LLM_API_ENDPOINT,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )

        # Control flags
        self._cancel_requested = False
        self._pause_requested = False

    def set_progress_callback(self, callback) -> None:
        """Set progress callback function."""
        self.progress_reporter.set_callback(callback)

    def request_cancel(self) -> None:
        """Request cancellation of extraction."""
        self._cancel_requested = True

    def request_pause(self, pause: bool) -> None:
        """Request pause or resume of extraction."""
        self._pause_requested = pause

    async def _check_pause(self) -> None:
        """Check and handle pause request."""
        while self._pause_requested and not self._cancel_requested:
            await asyncio.sleep(0.5)

    def _get_parser_for_file(self, file_path: Path):
        """Get appropriate parser for file type."""
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            return self.pdf_parser
        if ext == ".docx":
            return self.docx_parser
        if ext in (".xlsx", ".xls"):
            return self.excel_parser
        return None

    async def extract_flows(
        self,
        document_folder: str,
        task_id: Optional[str] = None,
        batch_size: int = 20,
        confidence_threshold: int = 70,
    ) -> ExtractionResult:
        """Extract flow records from documents."""
        self._cancel_requested = False
        self._pause_requested = False

        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        result = ExtractionResult(task_id, document_folder=document_folder)

        # Stage 1: Scan documents
        self.progress_reporter.report(
            task_id, "scanning", 0, 1, f"Scanning directory: {document_folder}"
        )
        documents = self.scanner.scan_directory(document_folder)
        result.total_documents = len(documents)

        if not documents:
            self.progress_reporter.report(task_id, "completed", 1, 1, "No documents found")
            return result

        self.progress_reporter.report(
            task_id, "scanning", 1, 1, f"Found {len(documents)} documents"
        )

        # Stage 2: Process documents (serial for classification)
        stage2_docs = []
        for idx, doc_path in enumerate(documents):
            await self._check_pause()
            if self._cancel_requested:
                break

            self.progress_reporter.report(
                task_id,
                "parsing",
                idx + 1,
                len(documents),
                f"Processing: {doc_path.name}",
            )

            try:
                checkpoint = self.checkpoint_manager.load_checkpoint(task_id, doc_path.name)
                if checkpoint and checkpoint.get("status") in ("stage1_done", "completed"):
                    doc_result = self._stage1_result_from_checkpoint(doc_path, checkpoint)
                else:
                    doc_result = await self._process_document_stage1(
                        doc_path, task_id, confidence_threshold
                    )
                if doc_result:
                    completed_records = doc_result.get("completed_records")
                    if completed_records is not None:
                        result.flow_records.extend(completed_records)
                        result.per_document_stats[doc_path.name] = {
                            "record_count": len(completed_records)
                        }
                    else:
                        stage2_docs.append(doc_result)
                    result.processed_documents += 1
                    result.total_tables += int(doc_result.get("total_tables", 0) or 0)
                    result.flow_tables += len(doc_result.get("flow_tables", []))
            except Exception as e:
                logger.error("Failed to process document %s: %s", doc_path.name, e)
                result.failed_documents.append(doc_path.name)
                result.errors.append(
                    {"document": doc_path.name, "stage": "stage1", "error": str(e)}
                )

        if self._cancel_requested:
            self.progress_reporter.report(task_id, "completed", 1, 1, "Extraction cancelled")
            return result

        # Stage 3: Normalize flow tables (parallel)
        self.progress_reporter.report(
            task_id, "normalizing", 0, len(stage2_docs), "Starting normalization"
        )

        # Create parallel normalization tasks
        tasks = []
        for doc_result in stage2_docs:
            task = asyncio.create_task(
                self._process_document_stage2(doc_result, task_id, batch_size)
            )
            tasks.append(task)

        # Wait for all normalization tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                logger.error("Normalization failed: %s", res)
                result.errors.append({"stage": "stage2", "error": str(res)})
            elif res:
                result.flow_records.extend(res["records"])
                result.per_document_stats.update(res.get("stats", {}))

        result.total_records = len(result.flow_records)

        self.progress_reporter.report(
            task_id,
            "completed",
            1,
            1,
            f"Extraction completed: {result.total_records} records",
        )

        return result

    async def extract_flows_append(
        self,
        task_id: str,
        new_folder: str,
        batch_size: int = 20,
        confidence_threshold: int = 70,
    ) -> ExtractionResult:
        """Append extraction by processing an additional folder under an existing task."""
        return await self.extract_flows(
            document_folder=new_folder,
            task_id=task_id,
            batch_size=batch_size,
            confidence_threshold=confidence_threshold,
        )

    async def _process_document_stage1(
        self,
        doc_path: Path,
        task_id: str,
        confidence_threshold: int,
    ) -> Optional[Dict[str, Any]]:
        """Process document stage 1: parse and classify tables."""
        parser = self._get_parser_for_file(doc_path)
        if not parser:
            return None

        # Parse tables (run in thread pool since parsers are sync)
        loop = asyncio.get_running_loop()
        raw_tables = await loop.run_in_executor(None, parser.extract_raw_tables, doc_path)

        if not raw_tables:
            self.checkpoint_manager.save_checkpoint(
                task_id,
                doc_path.name,
                {
                    "document_name": doc_path.name,
                    "document_path": str(doc_path),
                    "status": "completed",
                    "total_tables": 0,
                    "flow_tables_count": 0,
                    "total_flow_rows": 0,
                    "flow_tables": [],
                    "errors": ["No tables extracted"],
                },
            )
            return None

        # Extract document portrait
        non_table_context = ""
        if hasattr(parser, "extract_non_table_context"):
            non_table_context = await loop.run_in_executor(
                None, parser.extract_non_table_context, doc_path
            )

        content_preview = "\n\n".join(
            table.get_preview(4) for table in raw_tables if table.get_preview(4)
        )

        portrait = await self.portrait_extractor.extract(
            doc_path.name, non_table_context, content_preview
        )

        # Classify tables
        flow_tables = []
        for table in raw_tables:
            await self._check_pause()
            if self._cancel_requested:
                break

            classification = await self.classifier.classify(table, doc_path.name)
            is_flow = classification.get("is_flow_table", False)
            confidence = classification.get("confidence", 0)

            if is_flow and confidence >= confidence_threshold:
                header_row_index = int(classification.get("header_row_index", -1) or -1)
                data_start_row = int(classification.get("data_start_row", 0) or 0)
                if header_row_index >= 0:
                    data_start_row = max(header_row_index + 1, data_start_row)
                data_start_row = min(max(0, data_start_row), len(table.rows))
                flow_tables.append(
                    {
                        "table": table,
                        "classification": classification,
                        "portrait": portrait,
                        "rows": table.rows[data_start_row:],
                        "data_start_row": data_start_row,
                    }
                )

        if not flow_tables:
            self.checkpoint_manager.save_checkpoint(
                task_id,
                doc_path.name,
                {
                    "document_name": doc_path.name,
                    "document_path": str(doc_path),
                    "status": "completed",
                    "total_tables": len(raw_tables),
                    "flow_tables_count": 0,
                    "total_flow_rows": 0,
                    "flow_tables": [],
                    "portrait": portrait,
                    "errors": [],
                },
            )
            return None

        checkpoint_tables = []
        total_flow_rows = 0
        for item in flow_tables:
            rows = item.get("rows", [])
            total_flow_rows += len(rows)
            table = item["table"]
            checkpoint_tables.append(
                {
                    "table_index": table.table_index,
                    "classification": item.get("classification", {}),
                    "data_start_row": item.get("data_start_row", 0),
                    "rows": rows,
                }
            )
        self.checkpoint_manager.save_checkpoint(
            task_id,
            doc_path.name,
            {
                "document_name": doc_path.name,
                "document_path": str(doc_path),
                "status": "stage1_done",
                "total_tables": len(raw_tables),
                "flow_tables_count": len(flow_tables),
                "total_flow_rows": total_flow_rows,
                "flow_tables": checkpoint_tables,
                "portrait": portrait,
                "errors": [],
            },
        )

        return {
            "doc_path": doc_path,
            "flow_tables": flow_tables,
            "portrait": portrait,
            "total_tables": len(raw_tables),
        }

    async def _process_document_stage2(
        self,
        doc_result: Dict[str, Any],
        task_id: str,
        batch_size: int,
    ) -> Optional[Dict[str, Any]]:
        """Process document stage 2: normalize flow tables."""
        doc_path = doc_result["doc_path"]
        flow_tables = doc_result["flow_tables"]
        portrait = doc_result["portrait"]

        records = []
        for ft in flow_tables:
            await self._check_pause()
            if self._cancel_requested:
                break

            table = ft["table"]
            rows = ft.get("rows") or table.rows
            data_start_row = int(ft.get("data_start_row", 0) or 0)

            # Process in batches
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                normalized = await self.normalizer.normalize(
                    batch, portrait, source_file=doc_path.name
                )

                for batch_offset, item in enumerate(normalized):
                    if item.get("is_valid", True):
                        record = FlowRecord(
                            source_file=doc_path.name,
                            original_row=data_start_row + i + batch_offset,
                            transaction_time=item.get("transaction_time", ""),
                            counterparty_name=item.get("counterparty_name", ""),
                            counterparty_account=item.get("counterparty_account", ""),
                            amount=item.get("amount", ""),
                            summary=item.get("summary", ""),
                            transaction_type=item.get("transaction_type", ""),
                        )
                        records.append(record)

        checkpoint = self.checkpoint_manager.load_checkpoint(task_id, doc_path.name) or {}
        checkpoint["status"] = "completed"
        checkpoint["processed_rows"] = sum(
            len(item.get("rows", [])) for item in checkpoint.get("flow_tables", [])
        )
        checkpoint["normalized_records"] = len(records)
        checkpoint["records"] = [record.to_dict() for record in records]
        self.checkpoint_manager.save_checkpoint(task_id, doc_path.name, checkpoint)

        return {
            "doc_path": doc_path,
            "records": records,
            "stats": {doc_path.name: {"record_count": len(records)}},
        }

    def _stage1_result_from_checkpoint(
        self,
        doc_path: Path,
        checkpoint: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Rehydrate stage-1 data from a saved checkpoint."""
        if checkpoint.get("status") == "completed" and checkpoint.get("records"):
            records = []
            for item in checkpoint.get("records", []):
                records.append(
                    FlowRecord(
                        source_file=item.get("source_file", doc_path.name),
                        original_row=int(item.get("original_row", 0) or 0),
                        transaction_time=item.get("transaction_time", ""),
                        counterparty_name=item.get("counterparty_name", ""),
                        counterparty_account=item.get("counterparty_account", ""),
                        amount=item.get("amount", ""),
                        summary=item.get("summary", ""),
                        transaction_type=item.get("transaction_type", ""),
                    )
                )
            return {
                "doc_path": doc_path,
                "flow_tables": [],
                "portrait": checkpoint.get("portrait"),
                "total_tables": int(checkpoint.get("total_tables", 0) or 0),
                "completed_records": records,
            }

        flow_tables = []
        for item in checkpoint.get("flow_tables", []) or []:
            flow_tables.append(
                {
                    "table": RawTable(
                        table_index=int(item.get("table_index", 0) or 0),
                        rows=item.get("rows", []) or [],
                    ),
                    "classification": item.get("classification", {}),
                    "portrait": checkpoint.get("portrait"),
                    "rows": item.get("rows", []) or [],
                    "data_start_row": int(item.get("data_start_row", 0) or 0),
                }
            )
        if not flow_tables:
            return None
        return {
            "doc_path": doc_path,
            "flow_tables": flow_tables,
            "portrait": checkpoint.get("portrait"),
            "total_tables": int(checkpoint.get("total_tables", 0) or 0),
        }
