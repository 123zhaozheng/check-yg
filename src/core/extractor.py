# -*- coding: utf-8 -*-
"""
Flow Extractor - V2 wrapper for UI compatibility.
"""

from typing import Optional

from .flow_extractor_v2 import FlowExtractorV2
from .extraction_result import ExtractionResult


class FlowExtractor:
    """
    Backward-compatible wrapper that delegates to FlowExtractorV2.
    """

    def __init__(self, config=None):
        self._v2 = FlowExtractorV2(config)

    def set_progress_callback(self, callback) -> None:
        self._v2.set_progress_callback(callback)

    def request_cancel(self) -> None:
        self._v2.request_cancel()

    def request_pause(self, pause: bool) -> None:
        self._v2.request_pause(pause)

    def extract_flows(
        self,
        document_folder: str,
        task_id: Optional[str] = None,
        batch_size: int = 20,
        confidence_threshold: Optional[int] = None,
        parallelism: Optional[int] = None
    ) -> ExtractionResult:
        return self._v2.extract_flows(
            document_folder=document_folder,
            task_id=task_id,
            batch_size=batch_size,
            confidence_threshold=confidence_threshold,
            parallelism=parallelism
        )
