# -*- coding: utf-8 -*-
"""PDF parser using pdfplumber."""

import logging
import re
from pathlib import Path
from typing import List

import pdfplumber

from .base import BaseParser, RawTable

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF parser using pdfplumber for table extraction."""

    SUPPORTED_EXTENSIONS = ['.pdf']

    def extract_raw_tables(self, file_path: Path) -> List[RawTable]:
        """Extract raw tables from PDF using pdfplumber."""
        if not self.can_parse(file_path):
            return []

        try:
            tables = []
            with pdfplumber.open(file_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    try:
                        page_tables = page.extract_tables()
                        for table_idx, table in enumerate(page_tables):
                            raw_table = self._convert_table(table, page_idx * 100 + table_idx)
                            if raw_table and raw_table.rows:
                                tables.append(raw_table)
                    except Exception as e:
                        self.logger.warning("Failed to extract tables from page %d: %s", page_idx, e)
                        continue

            return tables

        except Exception as e:
            self.logger.error("Failed to extract raw tables from PDF %s: %s", file_path.name, e)
            return []

    def _convert_table(self, table_data: List[List], table_index: int) -> RawTable:
        """Convert pdfplumber table data to RawTable."""
        if not table_data:
            return None

        rows = []
        html_rows = []

        for row in table_data:
            cells = []
            for cell in row:
                cell_text = str(cell).strip() if cell is not None else ""
                cells.append(cell_text)

            # 跳过完全空的行
            if not any(cells):
                continue

            rows.append(cells)

            # 生成HTML行
            html_cells = ''.join(f'<td>{self._escape_html(cell)}</td>' for cell in cells)
            html_rows.append(f'<tr>{html_cells}</tr>')

        if not rows:
            return None

        html_content = f'<table>{"".join(html_rows)}</table>'

        return RawTable(
            table_index=table_index,
            html_content=html_content,
            rows=rows
        )

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

    def extract_non_table_context(self, file_path: Path, max_chars: int = 2000) -> str:
        """Extract non-table text from PDF."""
        try:
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            full_text = '\n'.join(text_parts)
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars]

            return full_text

        except Exception as e:
            self.logger.error("Failed to extract text from PDF %s: %s", file_path.name, e)
            return ""
