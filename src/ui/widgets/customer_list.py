# -*- coding: utf-8 -*-
"""
Customer list widget for displaying and editing customer names
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
    QPushButton, QLineEdit, QLabel
)
from PyQt5.QtCore import pyqtSignal

from ..styles import COLORS


class CustomerListWidget(QWidget):
    """Widget for displaying and managing customer name list"""
    
    customers_changed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Header with count
        header = QHBoxLayout()
        self.title_label = QLabel("客户名单")
        self.title_label.setStyleSheet(f"""
            font-size: 13px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        header.addWidget(self.title_label)
        
        self.count_label = QLabel("(0 人)")
        self.count_label.setStyleSheet(f"""
            font-size: 12px;
            color: {COLORS['text_secondary']};
        """)
        header.addWidget(self.count_label)
        header.addStretch()
        layout.addLayout(header)
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(200)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 4px;
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['primary']};
                color: {COLORS['text_white']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {COLORS['sidebar_hover']};
            }}
        """)
        layout.addWidget(self.list_widget)
        
        # Add customer input
        add_layout = QHBoxLayout()
        add_layout.setSpacing(8)
        
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("输入客户姓名...")
        self.add_input.setMinimumHeight(36)
        self.add_input.returnPressed.connect(self._add_customer)
        add_layout.addWidget(self.add_input)
        
        self.add_btn = QPushButton("添加")
        self.add_btn.setMinimumSize(60, 36)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: {COLORS['text_white']};
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
        """)
        self.add_btn.clicked.connect(self._add_customer)
        add_layout.addWidget(self.add_btn)
        layout.addLayout(add_layout)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.remove_btn = QPushButton("删除选中")
        self.remove_btn.setMinimumSize(80, 32)
        self.remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['card']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['sidebar_hover']};
            }}
        """)
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)
        
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setMinimumSize(60, 32)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['danger_light']};
                color: {COLORS['danger']};
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
                color: {COLORS['text_white']};
            }}
        """)
        self.clear_btn.clicked.connect(self._clear_all)
        btn_layout.addWidget(self.clear_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _add_customer(self) -> None:
        name = self.add_input.text().strip()
        if name:
            self.add_customer(name)
            self.add_input.clear()
    
    def _remove_selected(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_count()
        self._emit_changed()
    
    def _clear_all(self) -> None:
        self.list_widget.clear()
        self._update_count()
        self._emit_changed()
    
    def _update_count(self) -> None:
        count = self.list_widget.count()
        self.count_label.setText(f"({count} 人)")
    
    def _emit_changed(self) -> None:
        self.customers_changed.emit(self.get_customers())
    
    def add_customer(self, name: str) -> bool:
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).text() == name:
                return False
        
        self.list_widget.addItem(name)
        self._update_count()
        self._emit_changed()
        return True
    
    def set_customers(self, customers: list) -> None:
        self.list_widget.clear()
        for name in customers:
            self.list_widget.addItem(name)
        self._update_count()
    
    def get_customers(self) -> list:
        return [
            self.list_widget.item(i).text() 
            for i in range(self.list_widget.count())
        ]
    
    def clear(self) -> None:
        self._clear_all()
