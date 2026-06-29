# -*- coding: utf-8 -*-
"""Main extraction pipeline orchestrator."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import settings
from ...llm import DocumentPortraitExtractor, FlowDataNormalizer, FlowTableClassifier
from ...llm.classifier import _MAX_TOKENS_CLASSIFIER
from ...llm.normalizer import _MAX_TOKENS_NORMALIZER
from ...llm.portrait import _MAX_TOKENS_PORTRAIT
from ...models import LLMModel
from ...models.llm_model import THINKING_OFF as _MODEL_THINKING_OFF
from ...models.llm_model_assignment import (
    STAGE_CLASSIFICATION,
    STAGE_NORMALIZATION,
    STAGE_PORTRAIT,
)
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
        # Full paths of documents that reached stage 1, for path-aware append
        # dedup (same-named files in different folders are distinct).
        self.processed_document_paths: List[str] = []
        # S5 清洗不删减: every raw table row persisted 1:1. Unified list of
        # record dicts (standard / unparsed / excluded) with raw_payload. The
        # runner writes these into the ``flow_records`` table; ``flow_records``
        # (FlowRecord list above) is kept for backward compatibility with
        # downstream review/report/export services that still read
        # Document.flow_tables["records"].
        self.extracted_records: List[Dict[str, Any]] = []
        # Per-document portrait (account_type/holder/institution/...), keyed by
        # filename. Generated at stage 1 and carried through so the runner can
        # persist it onto the Document row (import page hover card reads it).
        # 不删减: a doc whose portrait extraction failed still gets an entry
        # with value None so the runner can clear / leave the column.
        self.per_document_portraits: Dict[str, Optional[Dict[str, Any]]] = {}

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
            "processed_document_paths": self.processed_document_paths,
            "extracted_records": self.extracted_records,
            "per_document_portraits": self.per_document_portraits,
        }


class FlowExtractor:
    """Async flow extraction pipeline."""

    def __init__(
        self,
        runtime_settings: Optional[Dict[str, str]] = None,
        stage_models: Optional[Dict[str, Optional[LLMModel]]] = None,
    ):
        runtime_settings = runtime_settings or {}
        stage_models = stage_models or {}
        llm_timeout = self._int_setting(
            runtime_settings.get("llm.timeout"),
            settings.LLM_TIMEOUT,
            minimum=1,
            maximum=600,
        )
        self.scanner = DocumentScanner()
        self.checkpoint_manager = CheckpointManager()
        self.progress_reporter = ProgressReporter()

        # Initialize parsers
        mineru_timeout = self._int_setting(
            runtime_settings.get("mineru.timeout"),
            settings.MINERU_TIMEOUT,
            minimum=1,
            maximum=3600,
        )
        self.pdf_parser = PDFParser(
            mineru_mode=runtime_settings.get("mineru.mode") or settings.MINERU_MODE,
            mineru_url=runtime_settings.get("mineru.url") or settings.MINERU_URL,
            mineru_public_url=runtime_settings.get("mineru.public_url") or settings.MINERU_PUBLIC_URL,
            mineru_public_api_key=runtime_settings.get("mineru.public_api_key")
            or settings.MINERU_PUBLIC_API_KEY,
            timeout=mineru_timeout,
        )
        self.excel_parser = ExcelParser()
        self.docx_parser = DocxParser()

        # Initialize LLM components. Per-stage resolution priority
        # (prd ②): 阶段卡片 > runtime ``llm.*`` 设置项 > 模块硬编码兜底常量.
        # ``stage_models`` is queried by the runner from DB (avoid extractor
        # touching DB directly). Missing card (None) falls back to runtime
        # ``llm.*`` settings + module constants — never crashes.
        self.classifier = FlowTableClassifier(
            **self._resolve_stage_llm_params(
                stage_models.get(STAGE_CLASSIFICATION),
                runtime_settings,
                llm_timeout,
                fallback_max_tokens=_MAX_TOKENS_CLASSIFIER,
            )
        )
        self.normalizer = FlowDataNormalizer(
            **self._resolve_stage_llm_params(
                stage_models.get(STAGE_NORMALIZATION),
                runtime_settings,
                llm_timeout,
                fallback_max_tokens=_MAX_TOKENS_NORMALIZER,
            )
        )
        self.portrait_extractor = DocumentPortraitExtractor(
            **self._resolve_stage_llm_params(
                stage_models.get(STAGE_PORTRAIT),
                runtime_settings,
                llm_timeout,
                fallback_max_tokens=_MAX_TOKENS_PORTRAIT,
            )
        )

        # Control flags
        self._cancel_requested = False
        self._pause_requested = False

    @staticmethod
    def _resolve_stage_llm_params(
        model: Optional[LLMModel],
        runtime_settings: Dict[str, str],
        llm_timeout: int,
        fallback_max_tokens: int,
    ) -> Dict[str, Any]:
        """Resolve per-stage LLM params (priority: card > env settings > module fallback).

        06-23-tab 决策：去掉 runtime ``llm.*`` 设置项中间兜底层（前端「集成与模型」
        底部 llm.* 容器已删，extractor 不再读 runtime llm.* 作 fallback）。卡片未
        指派时回退到环境变量 ``settings.LLM_*`` + 模块硬编码常量。``llm.timeout`` 仍
        从 runtime 读（超时不是卡片字段）。

        Args:
            model: 该阶段指派的卡片（None → 回退 env settings / 模块常量）。
            runtime_settings: runtime 设置项（仅读 ``llm.timeout``，已由调用方解析）。
            llm_timeout: LLM 超时（从 runtime settings 读，不来自卡片）。
            fallback_max_tokens: 模块硬编码兜底常量（卡片 max_tokens 缺时用）。

        Returns:
            ``{api_url, api_key, model, timeout, max_tokens, thinking}`` 供三模块
            构造器展开。``thinking``：卡片是 reasoning 模型且 default_thinking≠off
            时传 low/medium/high；否则 None（不给非 reasoning 模型发
            reasoning_effort，research §3）。
        """
        # 兜底层：环境变量 settings.LLM_*（不再读 runtime llm.* 中间层）。
        env_base_url = settings.LLM_API_ENDPOINT
        env_api_key = settings.LLM_API_KEY
        env_model = settings.LLM_MODEL_NAME

        if model is None:
            # 未指派卡片 → env settings + 模块常量兜底。
            return {
                "api_url": env_base_url,
                "api_key": env_api_key,
                "model": env_model,
                "timeout": llm_timeout,
                "max_tokens": fallback_max_tokens,
                "thinking": None,
                "temperature": None,
            }

        # 指派了卡片：从卡片读（卡片字段空时回退 env settings）。
        thinking = model.default_thinking
        if thinking == _MODEL_THINKING_OFF or not model.is_reasoning:
            thinking = None
        card_temperature = (
            model.default_temperature if model.default_temperature is not None else None
        )
        logger.info(
            "阶段使用模型卡片: display_name=%s, model=%s, max_tokens=%d, thinking=%s, is_reasoning=%s",
            model.display_name,
            model.model_name,
            model.default_max_tokens,
            model.default_thinking,
            model.is_reasoning,
        )
        return {
            "api_url": model.provider_base_url or env_base_url,
            "api_key": model.api_key or env_api_key,
            "model": model.model_name or env_model,
            "timeout": llm_timeout,
            "max_tokens": model.default_max_tokens or fallback_max_tokens,
            "thinking": thinking,
            "temperature": card_temperature,
        }

    @staticmethod
    def _int_setting(value: Optional[str], default: int, minimum: int, maximum: int) -> int:
        """Read a bounded integer runtime setting."""
        try:
            parsed = int(value) if value is not None else default
        except (TypeError, ValueError):
            parsed = default
        return min(max(parsed, minimum), maximum)

    @staticmethod
    def _infer_transaction_type(
        raw_amount: str,
        amount_sign_rule: str,
        portrait: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        根据 raw_amount 正负号与 amount_sign_rule 推断 transaction_type

        信用卡账户交由 LLM 按交易语义判断（符号规则反直觉），返回 None。
        返回 "收入" 或 "支出"，无法确定时返回 None。
        """
        if not raw_amount:
            return None

        # Credit card mode: rely on LLM semantic judgment.
        if portrait and portrait.get("account_type") == "credit_card":
            return None

        raw = str(raw_amount).strip()
        has_negative = raw.startswith("-")

        if amount_sign_rule == "pos_income":
            return "支出" if has_negative else "收入"
        if amount_sign_rule == "pos_expense":
            return "收入" if has_negative else "支出"
        if amount_sign_rule == "split_cols":
            return None  # LLM handles split columns
        if amount_sign_rule == "no_sign":
            return None  # rely on LLM/summary
        if amount_sign_rule == "unknown":
            if has_negative:
                return "支出"
            return None
        return None

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

    @staticmethod
    def _raw_payload_from_row(row: List[str]) -> Dict[str, Any]:
        """Capture a raw table row as a JSONB-safe payload (清洗不删减).

        Cells are stringified so JSONB stores them verbatim; the column count
        is preserved so the original row can be reconstructed exactly.
        """
        return {"cells": [str(c) if c is not None else "" for c in row]}

    @staticmethod
    def _build_record(
        *,
        record_type: str,
        source_file: str,
        row_index: int,
        raw_row: List[str],
        is_valid: bool = True,
        transaction_time: str = "",
        counterparty_name: str = "",
        counterparty_account: str = "",
        amount: str = "",
        raw_amount: str = "",
        summary: str = "",
        transaction_type: str = "",
        balance: str = "",
        exclude_reason: str = "",
    ) -> Dict[str, Any]:
        """Build one unified record dict for the ``extracted_records`` list.

        ``record_type`` ∈ {standard, unparsed, excluded}. ``raw_row`` is the
        original cell list — always captured into ``raw_payload`` so any
        filtered row can be restored verbatim (清洗不删减).
        """
        return {
            "record_type": record_type,
            "source_file": source_file,
            "row_index": int(row_index),
            "is_valid": bool(is_valid),
            "transaction_time": transaction_time or "",
            "counterparty_name": counterparty_name or "",
            "counterparty_account": counterparty_account or "",
            "amount": amount or "",
            "raw_amount": raw_amount or "",
            "summary": summary or "",
            "transaction_type": transaction_type or "",
            "balance": balance or "",
            "raw_payload": FlowExtractor._raw_payload_from_row(raw_row),
            "exclude_reason": exclude_reason or "",
        }

    async def extract_flows(
        self,
        document_folder: str,
        task_id: Optional[str] = None,
        batch_size: int = 20,
        confidence_threshold: int = 70,
        documents: Optional[List[Path]] = None,
        mineru_concurrency: int = 1,
        llm_concurrency: int = 2,
    ) -> ExtractionResult:
        """Extract flow records from documents.

        When ``documents`` is supplied (append path), scanning is skipped and
        only those pre-filtered documents are processed.

        ``mineru_concurrency`` caps stage-1 document parsing (MinerU fetch +
        classify + portrait) via an asyncio.Semaphore; ``llm_concurrency``
        caps stage-2 normalization. Defaults (1 / 2) start conservative —
        public MinerU is easily rate-limited.
        """
        self._cancel_requested = False
        self._pause_requested = False

        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        result = ExtractionResult(task_id, document_folder=document_folder)

        # Stage 1: Scan documents (unless a pre-filtered set was supplied)
        if documents is None:
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
        logger.info("扫描完成，共发现 %d 个文档", len(documents))

        # Stage 1: 逐文档解析 + 分类 + 画像（受 mineru_concurrency 信号量限流的并发）
        logger.info("阶段1开始：逐文档表格识别与流水判定（并发=%d）", mineru_concurrency)
        stage1_sem = asyncio.Semaphore(max(1, mineru_concurrency))
        total_docs = len(documents)
        # Shared progress counter — documents complete out of order under
        # concurrency, so we just advance a running count rather than the loop
        # index.
        progress_counter = {"done": 0}

        async def _stage1_one(doc_path: Path) -> Optional[Dict[str, Any]]:
            async with stage1_sem:
                await self._check_pause()
                if self._cancel_requested:
                    return None
                logger.info("阶段1处理文档: %s", doc_path.name)
                progress_counter["done"] += 1
                self.progress_reporter.report(
                    task_id,
                    "parsing",
                    progress_counter["done"],
                    total_docs,
                    f"Processing: {doc_path.name}",
                )
                try:
                    checkpoint = self.checkpoint_manager.load_checkpoint(
                        task_id, doc_path.name, document_path=str(doc_path)
                    )
                    if checkpoint and checkpoint.get("status") in ("stage1_done", "completed"):
                        return self._stage1_result_from_checkpoint(doc_path, checkpoint)
                    return await self._process_document_stage1(
                        doc_path, task_id, confidence_threshold
                    )
                except Exception as e:
                    logger.error("Failed to process document %s: %s", doc_path.name, e)
                    result.failed_documents.append(doc_path.name)
                    result.errors.append(
                        {"document": doc_path.name, "stage": "stage1", "error": str(e)}
                    )
                    return None

        stage1_results = await asyncio.gather(*[_stage1_one(p) for p in documents])

        stage2_docs: List[Dict[str, Any]] = []
        for doc_path, doc_result in zip(documents, stage1_results):
            if self._cancel_requested:
                break
            # 无论 stage1 是否产出表格/画像（0 表格、不支持格式、stage1 异常、
            # checkpoint 命中但 flow_tables 为空 都会返回 None），该文档都已被
            # "处理过"——必须先登记路径到 processed_document_paths，否则 runner
            # 批循环下一轮 _collect_pending_documents 会再次把它当 pending 收集，
            # 导致同一文档被无限重处理（CPU 拉满 + balance_check 每轮写库疯涨）。
            result.processed_documents += 1
            result.processed_document_paths.append(str(doc_path))
            if not doc_result:
                continue
            completed_records = doc_result.get("completed_records")
            if completed_records is not None:
                result.flow_records.extend(completed_records)
                result.per_document_stats[doc_path.name] = {
                    "record_count": len(completed_records)
                }
            else:
                stage2_docs.append(doc_result)
            # Capture the stage-1 portrait (may be None when extraction
            # failed) so the runner can persist it onto the Document row.
            result.per_document_portraits[doc_path.name] = doc_result.get("portrait")
            # S5 不删减: carry excluded rows (classifier-rejected tables)
            # into the unified record list even at stage 1, so they are
            # persisted regardless of whether stage 2 runs.
            excluded_records = doc_result.get("excluded_records") or []
            if excluded_records:
                result.extracted_records.extend(excluded_records)
            result.total_tables += int(doc_result.get("total_tables", 0) or 0)
            result.flow_tables += len(doc_result.get("flow_tables", []))

        if self._cancel_requested:
            self.progress_reporter.report(task_id, "completed", 1, 1, "Extraction cancelled")
            return result

        # Stage 2: 流水行标准化（受 llm_concurrency 信号量限流的并发）
        logger.info("阶段2开始：流水行标准化（并发=%d）", llm_concurrency)
        self.progress_reporter.report(
            task_id, "normalizing", 0, len(stage2_docs), "Starting normalization"
        )

        # Create parallel normalization tasks, each gated by the llm semaphore.
        stage2_sem = asyncio.Semaphore(max(1, llm_concurrency))

        async def _stage2_one(doc_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with stage2_sem:
                await self._check_pause()
                if self._cancel_requested:
                    return None
                return await self._process_document_stage2(doc_result, task_id, batch_size)

        results = await asyncio.gather(
            *[_stage2_one(dr) for dr in stage2_docs], return_exceptions=True
        )

        for res in results:
            if isinstance(res, Exception):
                logger.error("Normalization failed: %s", res)
                result.errors.append({"stage": "stage2", "error": str(res)})
            elif res:
                result.flow_records.extend(res["records"])
                result.per_document_stats.update(res.get("stats", {}))
                # S5 不删减: stage 2 emits the unified record list (standard +
                # unparsed) with raw_payload — extend the result's canonical list.
                result.extracted_records.extend(res.get("extracted_records", []))

        result.total_records = len(result.flow_records)
        logger.info(
            "提取完成：%d 条流水，失败文档 %d 个",
            result.total_records,
            len(result.failed_documents),
        )

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
        existing_document_paths: Optional[List[str]] = None,
        mineru_concurrency: int = 1,
        llm_concurrency: int = 2,
    ) -> ExtractionResult:
        """Append extraction by processing an additional folder under an existing task.

        Documents whose full path was already processed in a prior run
        (``existing_document_paths``) are skipped — so a same-named file in a
        new folder is still processed, while the exact same file is not
        re-extracted. Mirrors ``src/core/flow_extractor_v2.py`` append dedup.
        """
        self.progress_reporter.report(
            task_id, "scanning", 0, 1, f"Scanning directory: {new_folder}"
        )
        all_documents = self.scanner.scan_directory(new_folder)

        existing = {
            Path(str(p)).as_posix() for p in (existing_document_paths or [])
        }
        new_documents = [
            doc for doc in all_documents if doc.as_posix() not in existing
        ]
        skipped = len(all_documents) - len(new_documents)
        if skipped:
            logger.info("Append skipped %d already-processed document(s)", skipped)
        return await self.extract_flows(
            document_folder=new_folder,
            task_id=task_id,
            batch_size=batch_size,
            confidence_threshold=confidence_threshold,
            documents=new_documents,
            mineru_concurrency=mineru_concurrency,
            llm_concurrency=llm_concurrency,
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

        # Parse tables + non-table context in one MinerU fetch when supported
        # (avoids a second MinerU API call for the same PDF).
        loop = asyncio.get_running_loop()
        if hasattr(parser, "extract_tables_and_context"):
            raw_tables, non_table_context = await loop.run_in_executor(
                None, parser.extract_tables_and_context, doc_path
            )
        else:
            raw_tables = await loop.run_in_executor(None, parser.extract_raw_tables, doc_path)
            non_table_context = ""
            if hasattr(parser, "extract_non_table_context"):
                non_table_context = await loop.run_in_executor(
                    None, parser.extract_non_table_context, doc_path
                )

        logger.info("文档 %s 解析完成，抽取到表格 %d 个", doc_path.name, len(raw_tables))

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
                document_path=str(doc_path),
            )
            return None

        content_preview = "\n\n".join(
            table.get_preview(4) for table in raw_tables if table.get_preview(4)
        )

        logger.info("开始提取文档画像: %s", doc_path.name)
        portrait = await self.portrait_extractor.extract(
            doc_path.name, non_table_context, content_preview
        )
        logger.info("文档画像提取完成: %s", doc_path.name)

        # Classify tables
        flow_tables = []
        excluded_records: List[Dict[str, Any]] = []
        for table in raw_tables:
            await self._check_pause()
            if self._cancel_requested:
                break

            classification = await self.classifier.classify(
                table, doc_path.name, document_portrait=portrait
            )
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
            else:
                # S5 不删减: classifier rejected this table (not flow, or
                # confidence below threshold) — keep every original row as an
                # ``excluded`` record with raw_payload so it can be restored
                # verbatim. Never drop the rows.
                if not is_flow:
                    reason = "classifier: not flow table"
                else:
                    reason = f"classifier: confidence {confidence} below threshold {confidence_threshold}"
                for row_idx, row in enumerate(table.rows):
                    excluded_records.append(
                        self._build_record(
                            record_type="excluded",
                            source_file=doc_path.name,
                            row_index=row_idx + 1,
                            raw_row=row,
                            is_valid=False,
                            exclude_reason=reason,
                        )
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
                document_path=str(doc_path),
            )
            # S5 不删减: even with no flow tables, return the excluded records
            # so the runner persists them. ``flow_tables=[]`` tells extract_flows
            # not to schedule stage 2 for this doc.
            return {
                "doc_path": doc_path,
                "flow_tables": [],
                "portrait": portrait,
                "total_tables": len(raw_tables),
                "excluded_records": excluded_records,
            }

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
            document_path=str(doc_path),
        )

        return {
            "doc_path": doc_path,
            "flow_tables": flow_tables,
            "portrait": portrait,
            "total_tables": len(raw_tables),
            "excluded_records": excluded_records,
        }

    async def _process_document_stage2(
        self,
        doc_result: Dict[str, Any],
        task_id: str,
        batch_size: int,
    ) -> Optional[Dict[str, Any]]:
        """Process document stage 2: normalize flow tables.

        S5 不删减: normalizer 输出的每一行都保留。is_valid=true → standard
        记录（+ FlowRecord 兼容下游）；is_valid=false → unparsed 记录（带
        raw_payload + exclude_reason）。两者都不丢。
        """
        doc_path = doc_result["doc_path"]
        flow_tables = doc_result["flow_tables"]
        portrait = doc_result["portrait"]

        records: List[FlowRecord] = []
        extracted_records: List[Dict[str, Any]] = []
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

                # Post-processing: code-based transaction_type inference.
                # Applied to standard (is_valid=true) rows only — unparsed rows
                # are noise (totals/balances/headers) and stay as-is. Logic is
                # faithful to legacy src/core/flow_extractor_v2.py.
                amount_sign_rule = (portrait or {}).get("amount_sign_rule", "unknown")
                for item in normalized:
                    if not item.get("is_valid", True):
                        continue
                    raw_amount = str(item.get("raw_amount", "") or "")
                    inferred_type = self._infer_transaction_type(
                        raw_amount, amount_sign_rule, portrait
                    )
                    if inferred_type and item.get("transaction_type") != inferred_type:
                        logger.info(
                            "代码修正收支类型: %s raw_amount=%s LLM=%s → 代码=%s (rule=%s)",
                            doc_path.name,
                            raw_amount,
                            item.get("transaction_type"),
                            inferred_type,
                            amount_sign_rule,
                        )
                        item["transaction_type"] = inferred_type

                for batch_offset, item in enumerate(normalized):
                    row_index = data_start_row + i + batch_offset
                    raw_row = (
                        rows[i + batch_offset]
                        if 0 <= i + batch_offset < len(rows)
                        else []
                    )
                    is_valid = bool(item.get("is_valid", True))
                    if is_valid:
                        record = FlowRecord(
                            source_file=doc_path.name,
                            original_row=row_index,
                            transaction_time=item.get("transaction_time", ""),
                            counterparty_name=item.get("counterparty_name", ""),
                            counterparty_account=item.get("counterparty_account", ""),
                            amount=item.get("amount", ""),
                            summary=item.get("summary", ""),
                            transaction_type=item.get("transaction_type", ""),
                        )
                        records.append(record)
                        extracted_records.append(
                            self._build_record(
                                record_type="standard",
                                source_file=doc_path.name,
                                row_index=row_index,
                                raw_row=raw_row,
                                is_valid=True,
                                transaction_time=item.get("transaction_time", ""),
                                counterparty_name=item.get("counterparty_name", ""),
                                counterparty_account=item.get("counterparty_account", ""),
                                amount=item.get("amount", ""),
                                raw_amount=str(item.get("raw_amount", "") or ""),
                                summary=item.get("summary", ""),
                                transaction_type=item.get("transaction_type", ""),
                                balance=item.get("balance", ""),
                            )
                        )
                    else:
                        # S5 不删减: noise row (合计/小计/余额汇总行/页脚/页眉/空行)
                        # → unparsed, kept with raw_payload + normalizer fields.
                        extracted_records.append(
                            self._build_record(
                                record_type="unparsed",
                                source_file=doc_path.name,
                                row_index=row_index,
                                raw_row=raw_row,
                                is_valid=False,
                                transaction_time=item.get("transaction_time", ""),
                                counterparty_name=item.get("counterparty_name", ""),
                                counterparty_account=item.get("counterparty_account", ""),
                                amount=item.get("amount", ""),
                                raw_amount=str(item.get("raw_amount", "") or ""),
                                summary=item.get("summary", ""),
                                transaction_type=item.get("transaction_type", ""),
                                balance=item.get("balance", ""),
                                exclude_reason="normalizer: noise row (is_valid=false)",
                            )
                        )

        checkpoint = self.checkpoint_manager.load_checkpoint(
            task_id, doc_path.name, document_path=str(doc_path)
        ) or {}
        checkpoint["status"] = "completed"
        checkpoint["processed_rows"] = sum(
            len(item.get("rows", [])) for item in checkpoint.get("flow_tables", [])
        )
        checkpoint["normalized_records"] = len(records)
        checkpoint["records"] = [record.to_dict() for record in records]
        self.checkpoint_manager.save_checkpoint(
            task_id, doc_path.name, checkpoint, document_path=str(doc_path)
        )

        return {
            "doc_path": doc_path,
            "records": records,
            "extracted_records": extracted_records,
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
