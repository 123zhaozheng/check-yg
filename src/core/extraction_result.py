# -*- coding: utf-8 -*-
"""
Extraction result data structure for flow extraction.
"""

import logging
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..parsers.base import FlowRecord

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """流水提取结果"""
    task_id: str
    task_time: str
    document_folder: str
    total_documents: int
    processed_documents: int
    total_tables: int
    flow_tables: int
    total_records: int
    flow_records: List[FlowRecord] = field(default_factory=list)
    failed_documents: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)

    @property
    def total_amount(self) -> float:
        """计算总金额"""
        total = 0.0
        for record in self.flow_records:
            try:
                amount_str = record.amount.replace(',', '').replace('￥', '')
                amount_str = amount_str.replace('¥', '').replace('元', '')
                amount_str = amount_str.replace('+', '').replace('-', '')
                total += abs(float(amount_str))
            except (ValueError, TypeError, AttributeError):
                continue
        return total

    def to_dict(self) -> Dict:
        """转换为字典"""
        result: Dict[str, Any] = {
            "task_id": self.task_id,
            "task_time": self.task_time,
            "document_folder": self.document_folder,
            "total_documents": int(self.total_documents),
            "processed_documents": int(self.processed_documents),
            "total_tables": int(self.total_tables),
            "flow_tables": int(self.flow_tables),
            "total_records": int(self.total_records),
            "failed_documents": [str(doc) for doc in self.failed_documents],
            "errors": [self._to_json_safe_dict(err) for err in self.errors],
        }
        result['total_amount'] = self.total_amount
        result['flow_records'] = [r.to_dict() for r in self.flow_records]
        return result

    def to_json(self, ensure_ascii: bool = False, indent: int = 2) -> str:
        """转换为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, indent=indent)

    @staticmethod
    def _to_json_safe_dict(data: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key, value in data.items():
            safe[str(key)] = ExtractionResult._to_json_safe_value(value)
        return safe

    @staticmethod
    def _to_json_safe_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return ExtractionResult._to_json_safe_dict(value)
        if isinstance(value, list):
            return [ExtractionResult._to_json_safe_value(item) for item in value]
        return str(value)
