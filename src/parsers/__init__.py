# -*- coding: utf-8 -*-
"""Document parsers"""

from .base import BaseParser, ParseResult
from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .excel_parser import ExcelParser
from .html_parser import HTMLTableParser

__all__ = [
    'BaseParser', 'ParseResult',
    'PDFParser', 'DocxParser', 'ExcelParser', 'HTMLTableParser'
]
