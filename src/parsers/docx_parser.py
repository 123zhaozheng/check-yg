# -*- coding: utf-8 -*-
"""
DOCX parser using python-docx
"""

import logging
from pathlib import Path
from typing import List, Optional

from docx import Document
from docx.table import Table

from .base import BaseParser, RawTable

logger = logging.getLogger(__name__)


class DocxParser(BaseParser):
    """Parser for DOCX files using python-docx"""
    
    SUPPORTED_EXTENSIONS = ['.docx']
    
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
    
