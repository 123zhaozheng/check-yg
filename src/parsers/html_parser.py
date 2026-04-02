# -*- coding: utf-8 -*-
"""HTML table parser for extracting raw tables from HTML content."""

import logging
from typing import List, Optional

from bs4 import BeautifulSoup

from .base import RawTable

logger = logging.getLogger(__name__)


class HTMLTableParser:
    """Parser for extracting raw HTML tables."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def extract_raw_tables_from_html(self, html_content: str) -> List[RawTable]:
        """
        从HTML内容中提取原始表格数据（用于AI分析）
        
        Args:
            html_content: HTML字符串
            
        Returns:
            List[RawTable]: 原始表格列表
        """
        tables = []
        soup = BeautifulSoup(html_content, 'lxml')
        
        for idx, table_elem in enumerate(soup.find_all('table')):
            raw_table = self._parse_raw_table(table_elem, idx)
            if raw_table and raw_table.rows:
                tables.append(raw_table)
        
        return tables
    
    def _parse_raw_table(self, table_elem, table_index: int) -> Optional[RawTable]:
        """
        解析单个表格元素为原始表格数据
        
        Args:
            table_elem: BeautifulSoup table元素
            table_index: 表格索引
            
        Returns:
            RawTable对象
        """
        rows = []
        
        # 提取所有行（包括表头）
        for tr in table_elem.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells:
                rows.append(cells)
        
        if not rows:
            return None
        
        # 保存原始HTML
        html_content = str(table_elem)
        
        return RawTable(
            table_index=table_index,
            html_content=html_content,
            rows=rows
        )
