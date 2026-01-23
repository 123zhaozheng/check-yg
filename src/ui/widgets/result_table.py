# -*- coding: utf-8 -*-
"""
Result table widget for displaying audit matches
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QComboBox, QLabel,
    QPushButton, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush

from ..styles import COLORS


class ResultTable(QWidget):
    """
    Table widget for displaying audit match results
    Supports filtering by risk level and confidence
    """
    
    export_requested = pyqtSignal()
    
    COLUMNS = [
        ("客户姓名", 80),
        ("匹配文本", 80),
        ("匹配类型", 80),
        ("置信度", 60),
        ("来源文件", 140),
        ("交易时间", 140),
        ("交易金额", 100),
        ("收支类型", 70),
        ("摘要", 120),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_data = []
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Filter bar
        filter_layout = QHBoxLayout()
        
        filter_label = QLabel("筛选:")
        filter_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        filter_layout.addWidget(filter_label)
        
        self.confidence_filter = QComboBox()
        self.confidence_filter.addItems(["全部", "精确匹配", "脱敏匹配", "模糊匹配"])
        self.confidence_filter.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.confidence_filter)
        
        filter_layout.addStretch()
        
        # Export button
        self.export_btn = QPushButton("导出 Excel")
        self.export_btn.setObjectName("primary_btn")
        self.export_btn.setMinimumSize(100, 36)
        self.export_btn.clicked.connect(self.export_requested.emit)
        filter_layout.addWidget(self.export_btn)
        
        layout.addLayout(filter_layout)
        
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
        """Set table data from list of AuditMatch objects"""
        self._all_data = matches
        self._populate_table(matches)
    
    def _populate_table(self, matches: list) -> None:
        """Populate table with match data"""
        self.table.setRowCount(len(matches))
        
        for row, match in enumerate(matches):
            # Extract filename from path
            import os
            filename = os.path.basename(match.source_file)
            
            data = [
                match.customer_name,
                match.matched_text,
                match.confidence,
                f"{match.confidence_score}%",
                filename,
                match.transaction_time,
                match.amount,
                match.transaction_type,
                match.summary,
            ]
            
            for col, value in enumerate(data):
                item = QTableWidgetItem(str(value) if value else "")
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                
                # Color code confidence column - 使用前景色而不是背景色
                if col == 2:  # Confidence type
                    if "精确" in str(value):
                        item.setForeground(QBrush(QColor(COLORS['success'])))
                    elif "脱敏" in str(value):
                        item.setForeground(QBrush(QColor(COLORS['warning'])))
                    else:
                        item.setForeground(QBrush(QColor(COLORS['danger'])))
                
                self.table.setItem(row, col, item)
        
        # 调整行高
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, 36)
    
    def _apply_filter(self, filter_text: str) -> None:
        """Apply confidence filter"""
        if filter_text == "全部":
            self._populate_table(self._all_data)
        else:
            filtered = [m for m in self._all_data if m.confidence == filter_text]
            self._populate_table(filtered)
    
    def clear(self) -> None:
        """Clear table"""
        self._all_data = []
        self.table.setRowCount(0)
