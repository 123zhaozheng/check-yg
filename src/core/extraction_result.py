# -*- coding: utf-8 -*-
"""
Extraction result data structure for flow extraction.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

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
        from dataclasses import asdict
        result = asdict(self)
        result['total_amount'] = self.total_amount
        result['flow_records'] = [r.to_dict() for r in self.flow_records]
        return result
