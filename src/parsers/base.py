# -*- coding: utf-8 -*-
"""
Base parser class and common data structures
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


# 完整流水Excel的列结构
FLOW_EXCEL_COLUMNS = [
    '来源文件',
    '原始行号',
    '交易时间',
    '交易对手名',
    '交易对手账号',
    '金额',
    '摘要',
    '收支类型',
]


# ============ 流水记录 ============

@dataclass
class FlowRecord:
    """单条流水记录（标准化后）"""
    source_file: str = ""
    original_row: int = 0
    transaction_time: str = ""
    counterparty_name: str = ""
    counterparty_account: str = ""
    amount: str = ""
    summary: str = ""
    transaction_type: str = ""
    
    def to_list(self) -> List[str]:
        """转换为Excel行数据"""
        return [
            self.source_file,
            str(self.original_row),
            self.transaction_time,
            self.counterparty_name,
            self.counterparty_account,
            self.amount,
            self.summary,
            self.transaction_type,
        ]
    
    def to_dict(self) -> Dict[str, str]:
        return {
            'source_file': self.source_file,
            'original_row': str(self.original_row),
            'transaction_time': self.transaction_time,
            'counterparty_name': self.counterparty_name,
            'counterparty_account': self.counterparty_account,
            'amount': self.amount,
            'summary': self.summary,
            'transaction_type': self.transaction_type,
        }


# ============ 原始表格数据 ============

@dataclass
class RawTable:
    """原始表格数据（未经AI处理）"""
    table_index: int = 0
    html_content: str = ""
    rows: List[List[str]] = field(default_factory=list)
    
    @property
    def row_count(self) -> int:
        return len(self.rows)
    
    def get_preview(self, max_rows: int = 5) -> str:
        """获取表格预览（前N行的HTML）"""
        if not self.rows:
            return ""
        preview_rows = self.rows[:max_rows]
        html_rows = []
        for row in preview_rows:
            cells = ''.join(f'<td>{cell}</td>' for cell in row)
            html_rows.append(f'<tr>{cells}</tr>')
        return f'<table>{"".join(html_rows)}</table>'


class BaseParser(ABC):
    """Abstract base class for document parsers"""
    
    # Supported file extensions for this parser
    SUPPORTED_EXTENSIONS: List[str] = []
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    @abstractmethod
    def extract_raw_tables(self, file_path: Path) -> List[RawTable]:
        """Extract raw tables for downstream AI processing."""
