# -*- coding: utf-8 -*-
"""
Result table widget for displaying review matches
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt

from ..styles import COLORS


class ResultTable(QWidget):
    """
    Table widget for displaying review match results
    """
    
    COLUMNS = [
        ("匹配用户", 100),
        ("来源文件", 140),
        ("交易时间", 140),
        ("对手名", 120),
        ("对手账号", 140),
        ("金额", 100),
        ("摘要", 160),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_data = []
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        
        # Set column widths
        header = self.table.horizontalHeader()
        for i, (_, width) in enumerate(self.COLUMNS):
            self.table.setColumnWidth(i, width)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        # Table styling - 修复选中状态文字颜色问题
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                gridline-color: {COLORS['border_light']};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 6px 8px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: {COLORS['primary_light']};
                color: {COLORS['text_primary']};
            }}
            QTableWidget::item:alternate {{
                background-color: {COLORS['sidebar']};
            }}
            QHeaderView::section {{
                background-color: {COLORS['sidebar']};
                color: {COLORS['text_primary']};
                font-weight: 600;
                font-size: 12px;
                padding: 8px 6px;
                border: none;
                border-bottom: 1px solid {COLORS['border']};
                border-right: 1px solid {COLORS['border_light']};
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
        """)
        
        layout.addWidget(self.table)
    
    def set_data(self, matches: list) -> None:
        """Set table data from list of ReviewMatch dicts"""
        self._all_data = matches
        self._populate_table(matches)
    
    def _populate_table(self, matches: list) -> None:
        """Populate table with match data"""
        self.table.setRowCount(len(matches))
        
        for row, match in enumerate(matches):
            import os
            source_file = match.get("source_file", "")
            filename = os.path.basename(source_file)
            data = [
                match.get("customer_name", ""),
                filename,
                match.get("transaction_time", ""),
                match.get("counterparty_name", ""),
                match.get("counterparty_account", ""),
                match.get("amount", ""),
                match.get("summary", ""),
            ]
            for col, value in enumerate(data):
                item = QTableWidgetItem(str(value) if value else "")
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.table.setItem(row, col, item)
        
        # 调整行高
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, 36)
    
    def clear(self) -> None:
        """Clear table"""
        self._all_data = []
        self.table.setRowCount(0)
