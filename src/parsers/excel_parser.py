# -*- coding: utf-8 -*-
"""
Excel parser using openpyxl
将 Excel 转成 HTML 表格格式，由 LLM 智能识别字段
"""

import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple

import openpyxl

from .base import BaseParser, ParseResult, ParsedTable, TableRow, RawTable

logger = logging.getLogger(__name__)


class ExcelParser(BaseParser):
    """
    Parser for Excel files using openpyxl
    
    核心思路：
    - 不假设固定表头格式
    - 把每行转成 HTML 格式 <tr><td>...</td></tr>
    - 保留原始数据，由 LLM 后续智能识别字段
    """
    
    SUPPORTED_EXTENSIONS = ['.xlsx', '.xls']
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse Excel file"""
        if not self.can_parse(file_path):
            return self._create_error_result(
                file_path,
                f"Unsupported file type: {file_path.suffix}"
            )
        
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            
            tables = []
            raw_texts = []
            html_tables = []  # 存储 HTML 格式的表格
            
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                parsed, html_content = self._parse_sheet_to_html(ws, sheet_name)
                if parsed and parsed.rows:
                    tables.append(parsed)
                    html_tables.append(html_content)
                    
                    # Collect raw text (HTML 格式)
                    for row in parsed.rows:
                        raw_texts.append(row.raw_text)
            
            wb.close()
            
            return ParseResult(
                file_path=file_path,
                success=True,
                tables=tables,
                raw_text='\n'.join(raw_texts),
                metadata={
                    'parser': 'openpyxl',
                    'sheets': wb.sheetnames,
                    'html_tables': html_tables  # 完整的 HTML 表格，供调试或展示
                }
            )
            
        except Exception as e:
            self.logger.error("Failed to parse Excel %s: %s", file_path.name, e)
            return self._create_error_result(file_path, str(e))
    
    def _parse_sheet_to_html(self, ws, sheet_name: str) -> Tuple[Optional[ParsedTable], str]:
        """
        将工作表解析为 HTML 表格格式
        
        返回:
            - ParsedTable: 包含每行数据的结构
            - str: 完整的 HTML 表格字符串
        """
        rows = []
        html_rows = []
        
        row_idx = 0
        for row in ws.iter_rows(values_only=True):
            # 转换单元格为字符串
            cells = [self._cell_to_str(cell) for cell in row]
            
            # 跳过空行
            if not any(cells):
                continue
            
            # 构建 HTML 行格式: <tr><td>cell1</td><td>cell2</td>...</tr>
            td_elements = ''.join(f'<td>{self._escape_html(cell)}</td>' for cell in cells)
            html_row = f'<tr>{td_elements}</tr>'
            html_rows.append(html_row)
            
            # raw_text 使用 HTML 行格式，方便 LLM 理解表格结构
            table_row = TableRow(
                row_index=row_idx,
                cells=cells,
                raw_text=html_row
            )
            
            # 注意：不再尝试基于表头提取字段，全部交给 LLM 处理
            rows.append(table_row)
            row_idx += 1
        
        if not rows:
            return None, ""
        
        # 构建完整的 HTML 表格
        html_table = f'<table data-sheet="{sheet_name}">\n' + '\n'.join(html_rows) + '\n</table>'
        
        # 不再假设固定表头，headers 为空
        return ParsedTable(headers=[], rows=rows), html_table
    
    @staticmethod
    def _cell_to_str(cell: Any) -> str:
        """Convert cell value to string"""
        if cell is None:
            return ""
        return str(cell).strip()
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))
    
    # ============ 新增：原始表格提取方法 ============
    
    def extract_raw_tables(self, file_path: Path) -> List[RawTable]:
        """
        从Excel文件中提取原始表格数据（用于AI分析）
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            List[RawTable]: 原始表格列表
        """
        if not self.can_parse(file_path):
            return []
        
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            tables = []
            
            for sheet_idx, sheet_name in enumerate(wb.sheetnames):
                ws = wb[sheet_name]
                raw_table = self._parse_sheet_to_raw(ws, sheet_idx, sheet_name)
                if raw_table and raw_table.rows:
                    tables.append(raw_table)
            
            wb.close()
            return tables
            
        except Exception as e:
            self.logger.error("Failed to extract raw tables from Excel %s: %s", 
                            file_path.name, e)
            return []
    
    def _parse_sheet_to_raw(self, ws, table_index: int, sheet_name: str) -> Optional[RawTable]:
        """
        将工作表解析为原始表格数据
        
        Args:
            ws: openpyxl worksheet对象
            table_index: 表格索引
            sheet_name: 工作表名
            
        Returns:
            RawTable对象
        """
        rows = []
        
        for row in ws.iter_rows(values_only=True):
            cells = [self._cell_to_str(cell) for cell in row]
            
            # 跳过空行
            if not any(cells):
                continue
            
            rows.append(cells)
        
        if not rows:
            return None
        
        # 生成HTML格式的原始内容
        html_rows = []
        for row in rows:
            td_elements = ''.join(f'<td>{self._escape_html(cell)}</td>' for cell in row)
            html_rows.append(f'<tr>{td_elements}</tr>')
        
        html_content = f'<table data-sheet="{sheet_name}">\n' + '\n'.join(html_rows) + '\n</table>'
        
        return RawTable(
            table_index=table_index,
            html_content=html_content,
            rows=rows
        )
