# -*- coding: utf-8 -*-
"""
Base parser class and common data structures
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============ 标准字段定义 ============

class StandardField(Enum):
    """业务规定的6个标准字段"""
    TRANSACTION_TIME = 'transaction_time'
    COUNTERPARTY_NAME = 'counterparty_name'
    COUNTERPARTY_ACCOUNT = 'counterparty_account'
    AMOUNT = 'amount'
    SUMMARY = 'summary'
    TRANSACTION_TYPE = 'transaction_type'


STANDARD_FIELD_NAMES = {
    StandardField.TRANSACTION_TIME: '交易时间',
    StandardField.COUNTERPARTY_NAME: '交易对手名',
    StandardField.COUNTERPARTY_ACCOUNT: '交易对手账号',
    StandardField.AMOUNT: '金额',
    StandardField.SUMMARY: '摘要',
    StandardField.TRANSACTION_TYPE: '收支类型',
}

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


# ============ 表头映射相关 ============

@dataclass
class ColumnMapping:
    """列映射：标准字段 -> 原始列索引"""
    transaction_time: int = -1
    counterparty_name: int = -1
    counterparty_account: int = -1
    amount: int = -1
    summary: int = -1
    transaction_type: int = -1
    
    def to_dict(self) -> Dict[str, int]:
        return {
            'transaction_time': self.transaction_time,
            'counterparty_name': self.counterparty_name,
            'counterparty_account': self.counterparty_account,
            'amount': self.amount,
            'summary': self.summary,
            'transaction_type': self.transaction_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> 'ColumnMapping':
        return cls(
            transaction_time=data.get('transaction_time', -1),
            counterparty_name=data.get('counterparty_name', -1),
            counterparty_account=data.get('counterparty_account', -1),
            amount=data.get('amount', -1),
            summary=data.get('summary', -1),
            transaction_type=data.get('transaction_type', -1),
        )


@dataclass
class HeaderMapping:
    """表头映射结果"""
    is_flow_table: bool = False
    confidence: int = 0
    reason: str = ""
    header_row_index: int = 0
    data_start_row: int = 1
    column_mapping: ColumnMapping = field(default_factory=ColumnMapping)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'is_flow_table': self.is_flow_table,
            'confidence': self.confidence,
            'reason': self.reason,
            'header_row_index': self.header_row_index,
            'data_start_row': self.data_start_row,
            'column_mapping': self.column_mapping.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HeaderMapping':
        return cls(
            is_flow_table=data.get('is_flow_table', False),
            confidence=data.get('confidence', 0),
            reason=data.get('reason', ''),
            header_row_index=data.get('header_row_index', 0),
            data_start_row=data.get('data_start_row', 1),
            column_mapping=ColumnMapping.from_dict(data.get('column_mapping', {})),
        )


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


# ============ 原有数据结构（保留兼容） ============


@dataclass
class TableRow:
    """Represents a single row in a parsed table"""
    row_index: int
    cells: List[str]
    raw_text: str = ""
    
    # Common transaction fields (extracted if available)
    transaction_time: Optional[str] = None
    amount: Optional[str] = None
    counterparty: Optional[str] = None
    transaction_type: Optional[str] = None  # 收入/支出
    summary: Optional[str] = None


@dataclass
class ParsedTable:
    """Represents a parsed table from a document"""
    headers: List[str] = field(default_factory=list)
    rows: List[TableRow] = field(default_factory=list)
    source_page: int = 0
    
    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass
class ParseResult:
    """Result of parsing a document"""
    file_path: Path
    success: bool
    tables: List[ParsedTable] = field(default_factory=list)
    raw_text: str = ""
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_rows(self) -> int:
        return sum(t.row_count for t in self.tables)
    
    @property
    def has_tables(self) -> bool:
        return len(self.tables) > 0


class BaseParser(ABC):
    """Abstract base class for document parsers"""
    
    # Supported file extensions for this parser
    SUPPORTED_EXTENSIONS: List[str] = []
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        """
        Parse a document file
        
        Args:
            file_path: Path to the document
            
        Returns:
            ParseResult containing extracted data
        """
        pass
    
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def _create_error_result(self, file_path: Path, error: str) -> ParseResult:
        """Create an error result"""
        return ParseResult(
            file_path=file_path,
            success=False,
            error_message=error
        )
    
    def _extract_transaction_fields(self, row: TableRow, headers: List[str]) -> None:
        """
        Try to extract common transaction fields from a row
        
        This method attempts to identify and extract:
        - Transaction time
        - Amount
        - Counterparty name
        - Transaction type (income/expense)
        - Summary/remarks
        """
        if not headers or len(row.cells) != len(headers):
            return
        
        # Common header patterns (Chinese)
        time_patterns = ['时间', '日期', '交易时间', '记账时间', '付款时间']
        amount_patterns = ['金额', '交易金额', '付款金额', '收款金额', '转账金额']
        counterparty_patterns = ['对方', '对方户名', '交易对方', '收款方', '付款方', '对方姓名']
        type_patterns = ['类型', '交易类型', '收支', '收/支']
        summary_patterns = ['摘要', '备注', '说明', '交易说明', '附言']
        
        for i, header in enumerate(headers):
            header_lower = header.lower().strip()
            cell_value = row.cells[i].strip() if i < len(row.cells) else ""
            
            if not cell_value:
                continue
            
            # Match time
            if any(p in header_lower for p in time_patterns):
                row.transaction_time = cell_value
            
            # Match amount
            elif any(p in header_lower for p in amount_patterns):
                row.amount = cell_value
            
            # Match counterparty
            elif any(p in header_lower for p in counterparty_patterns):
                row.counterparty = cell_value
            
            # Match transaction type
            elif any(p in header_lower for p in type_patterns):
                row.transaction_type = cell_value
            
            # Match summary
            elif any(p in header_lower for p in summary_patterns):
                row.summary = cell_value
