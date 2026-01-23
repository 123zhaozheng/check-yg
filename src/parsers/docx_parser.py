# -*- coding: utf-8 -*-
"""
DOCX parser using python-docx
"""

import logging
from pathlib import Path
from typing import List, Optional

from docx import Document
from docx.table import Table

from .base import BaseParser, ParseResult, ParsedTable, TableRow, RawTable

logger = logging.getLogger(__name__)


class DocxParser(BaseParser):
    """Parser for DOCX files using python-docx"""
    
    SUPPORTED_EXTENSIONS = ['.docx']
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse DOCX file"""
        if not self.can_parse(file_path):
            return self._create_error_result(
                file_path,
                f"Unsupported file type: {file_path.suffix}"
            )
        
        try:
            doc = Document(file_path)
            
            # Extract text
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            raw_text = '\n'.join(paragraphs)
            
            # Extract tables
            tables = []
            for table in doc.tables:
                parsed = self._parse_table(table)
                if parsed and parsed.rows:
                    tables.append(parsed)
            
            return ParseResult(
                file_path=file_path,
                success=True,
                tables=tables,
                raw_text=raw_text,
                metadata={'parser': 'python-docx'}
            )
            
        except Exception as e:
            self.logger.error("Failed to parse DOCX %s: %s", file_path.name, e)
            return self._create_error_result(file_path, str(e))
    
    def extract_raw_tables(self, file_path: Path) -> List[RawTable]:
        """
        从DOCX文件提取原始表格数据
        
        Args:
            file_path: DOCX文件路径
            
        Returns:
            List[RawTable]: 原始表格列表
        """
        if not self.can_parse(file_path):
            return []
        
        try:
            doc = Document(file_path)
            raw_tables = []
            
            for table_index, table in enumerate(doc.tables):
                raw_table = self._table_to_raw(table, table_index)
                if raw_table:
                    raw_tables.append(raw_table)
            
            return raw_tables
            
        except Exception as e:
            self.logger.error("Failed to extract raw tables from DOCX %s: %s", file_path.name, e)
            return []
    
    def _table_to_raw(self, table: Table, table_index: int) -> Optional[RawTable]:
        """
        将docx表格转换为RawTable
        
        Args:
            table: python-docx Table对象
            table_index: 表格索引
            
        Returns:
            RawTable对象，空表格返回None
        """
        rows = []
        html_rows = []
        
        for row in table.rows:
            # 提取单元格文本，处理合并单元格
            cells = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                cells.append(cell_text)
            
            # 跳过完全空的行
            if not any(cells):
                continue
            
            rows.append(cells)
            
            # 生成HTML行
            html_cells = ''.join(f'<td>{cell}</td>' for cell in cells)
            html_rows.append(f'<tr>{html_cells}</tr>')
        
        # 空表格返回None
        if not rows:
            return None
        
        # 生成HTML内容
        html_content = f'<table>{"".join(html_rows)}</table>'
        
        return RawTable(
            table_index=table_index,
            html_content=html_content,
            rows=rows
        )
    
    def _parse_table(self, table: Table) -> ParsedTable:
        """Parse a docx table into ParsedTable"""
        headers = []
        rows = []
        
        for row_idx, row in enumerate(table.rows):
            cells = [cell.text.strip() for cell in row.cells]
            
            # First row as headers
            if row_idx == 0:
                headers = cells
                continue
            
            raw_text = ' | '.join(cells)
            table_row = TableRow(
                row_index=row_idx - 1,
                cells=cells,
                raw_text=raw_text
            )
            
            # Extract transaction fields
            self._extract_transaction_fields(table_row, headers)
            rows.append(table_row)
        
        return ParsedTable(headers=headers, rows=rows)
