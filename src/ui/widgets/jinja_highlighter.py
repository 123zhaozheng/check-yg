# -*- coding: utf-8 -*-
"""
Jinja2 syntax highlighter for QPlainTextEdit.
Highlights {{ variable }} patterns with subtle light blue.
"""

import re

from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor
from PyQt5.QtWidgets import QPlainTextEdit


class JinjaHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent.document())
        self._format = QTextCharFormat()
        self._format.setBackground(QColor("#E8F4FD"))
        self._format.setForeground(QColor("#1A73E8"))
        self._pattern = re.compile(r'\{\{.*?\}\}')

    def highlightBlock(self, text):
        for match in self._pattern.finditer(text):
            start = match.start()
            end = match.end()
            self.setFormat(start, end - start, self._format)
