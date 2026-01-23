# -*- coding: utf-8 -*-
"""
File selector widget for choosing files and directories
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QFileDialog
)
from PyQt5.QtCore import pyqtSignal

from ..styles import COLORS


class FileSelector(QWidget):
    """File/folder selector with browse button"""
    
    path_changed = pyqtSignal(str)
    
    def __init__(
        self, 
        placeholder: str = "选择文件...",
        mode: str = "file",
        file_filter: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)
        self.path_input.setReadOnly(True)
        self.path_input.setMinimumHeight(36)
        self.path_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                color: {COLORS['text_primary']};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
        """)
        layout.addWidget(self.path_input)
        
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.setMinimumSize(70, 36)
        self.browse_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['card']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['sidebar_hover']};
                border-color: {COLORS['text_light']};
            }}
        """)
        self.browse_btn.clicked.connect(self._browse)
        layout.addWidget(self.browse_btn)
    
    def _browse(self) -> None:
        if self.mode == "folder":
            path = QFileDialog.getExistingDirectory(
                self, "选择文件夹", "",
                QFileDialog.ShowDirsOnly
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", "",
                self.file_filter
            )
        
        if path:
            self.path_input.setText(path)
            self.path_changed.emit(path)
    
    def get_path(self) -> str:
        return self.path_input.text()
    
    def set_path(self, path: str) -> None:
        self.path_input.setText(path)
    
    def clear(self) -> None:
        self.path_input.clear()
