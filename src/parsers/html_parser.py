# -*- coding: utf-8 -*-
"""
HTML table parser for extracting tables from markdown/HTML content
"""

import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from .base import ParsedTable, TableRow, RawTable

logger = logging.getLogger(__name__)


class HTMLTableParser:
    """Parser for extracting tables from HTML content"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def extract_tables_from_html(self, html_content: str) -> List[ParsedTable]:
        """
        Extract all tables from HTML content
        
        Args:
            html_content: HTML string containing tables
            
        Returns:
            List of ParsedTable objects
        """
        tables = []
        soup = BeautifulSoup(html_content, 'lxml')
        
        for table_elem in soup.find_all('table'):
            parsed = self._parse_table_element(table_elem)
            if parsed and parsed.rows:
                tables.append(parsed)
        
        return tables
    
    def extract_tables_from_markdown(self, md_content: str) -> List[ParsedTable]:
        """
        Extract tables from markdown content
        Handles both HTML tables and markdown tables
        
        Args:
            md_content: Markdown string
            
        Returns:
            List of ParsedTable objects
        """
        tables = []
        
        # Extract HTML tables
        html_tables = self.extract_tables_from_html(md_content)
        tables.extend(html_tables)
        
        # Extract markdown tables (| col1 | col2 | format)
        md_tables = self._extract_markdown_tables(md_content)
        tables.extend(md_tables)
        
        return tables
    
    def _parse_table_element(self, table_elem) -> Optional[ParsedTable]:
        """Parse a BeautifulSoup table element"""
        headers = []
        rows = []
        
        # Extract headers from thead or first row
        thead = table_elem.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                headers = [
                    th.get_text(strip=True) 
                    for th in header_row.find_all(['th', 'td'])
                ]
        
        # Extract body rows
        tbody = table_elem.find('tbody') or table_elem
        row_index = 0
        
        for tr in tbody.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            
            # If no headers yet, use first row as headers
            if not headers and cells:
                headers = cells
                continue
            
            if cells:
                raw_text = ' | '.join(cells)
                table_row = TableRow(
                    row_index=row_index,
                    cells=cells,
                    raw_text=raw_text
                )
                rows.append(table_row)
                row_index += 1
        
        if not rows:
            return None
        
        parsed = ParsedTable(headers=headers, rows=rows)
        
        # Try to extract transaction fields
        for row in parsed.rows:
            self._extract_transaction_fields(row, headers)
        
        return parsed
    
    def _extract_markdown_tables(self, md_content: str) -> List[ParsedTable]:
        """Extract markdown-style tables"""
        tables = []
        
        # Pattern for markdown table rows
        table_pattern = re.compile(
            r'^\|(.+)\|$',
            re.MULTILINE
        )
        
        lines = md_content.split('\n')
        current_table_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                current_table_lines.append(stripped)
            else:
                if len(current_table_lines) >= 2:
                    table = self._parse_markdown_table(current_table_lines)
                    if table:
                        tables.append(table)
                current_table_lines = []
        
        # Handle last table
        if len(current_table_lines) >= 2:
            table = self._parse_markdown_table(current_table_lines)
            if table:
                tables.append(table)
        
        return tables
    
    def _parse_markdown_table(self, lines: List[str]) -> Optional[ParsedTable]:
        """Parse markdown table lines into ParsedTable"""
        if len(lines) < 2:
            return None
        
        # Parse header (first line)
        headers = [cell.strip() for cell in lines[0].strip('|').split('|')]
        
        # Skip separator line (second line with ---)
        start_idx = 1
        if len(lines) > 1 and re.match(r'^[\|\s\-:]+$', lines[1]):
            start_idx = 2
        
        rows = []
        for i, line in enumerate(lines[start_idx:]):
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            if cells:
                raw_text = ' | '.join(cells)
                row = TableRow(
                    row_index=i,
                    cells=cells,
                    raw_text=raw_text
                )
                rows.append(row)
        
        if not rows:
            return None
        
        parsed = ParsedTable(headers=headers, rows=rows)
        
        # Extract transaction fields
        for row in parsed.rows:
            self._extract_transaction_fields(row, headers)
        
        return parsed
    
    def _extract_transaction_fields(self, row: TableRow, headers: List[str]) -> None:
        """Extract common transaction fields from a row"""
        if not headers or len(row.cells) != len(headers):
            return
        
        time_patterns = ['时间', '日期', '交易时间', '记账时间', '付款时间']
        amount_patterns = ['金额', '交易金额', '付款金额', '收款金额', '转账金额']
        counterparty_patterns = ['对方', '对方户名', '交易对方', '收款方', '付款方', '对方姓名', '姓名']
        type_patterns = ['类型', '交易类型', '收支', '收/支']
        summary_patterns = ['摘要', '备注', '说明', '交易说明', '附言']
        
        for i, header in enumerate(headers):
            header_clean = header.strip()
            cell_value = row.cells[i].strip() if i < len(row.cells) else ""
            
            if not cell_value:
                continue
            
            if any(p in header_clean for p in time_patterns):
                row.transaction_time = cell_value
            elif any(p in header_clean for p in amount_patterns):
                row.amount = cell_value
            elif any(p in header_clean for p in counterparty_patterns):
                row.counterparty = cell_value
            elif any(p in header_clean for p in type_patterns):
                row.transaction_type = cell_value
            elif any(p in header_clean for p in summary_patterns):
                row.summary = cell_value
    
    # ============ 新增：原始表格提取方法 ============
    
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
