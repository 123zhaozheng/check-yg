# -*- coding: utf-8 -*-
"""
Progress Card widget for showing operation progress
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QProgressBar, 
    QPushButton, QHBoxLayout, QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal

from .card import Card
from ..styles import COLORS


class ProgressCard(Card):
    """
    Card for displaying progress of long-running operations
    Includes progress bar, status text, and log output
    """
    
    cancel_requested = pyqtSignal()
    
    def __init__(self, title: str = "处理进度", parent=None):
        super().__init__(parent, padding=20)
        
        # Title
        self.add_title(title)
        
        # Status label
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet(f"""
            font-size: 14px;
            color: {COLORS['text_secondary']};
            margin-bottom: 8px;
        """)
        self.layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['border_light']};
                border: none;
                border-radius: 6px;
                height: 12px;
                text-align: center;
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['primary']};
                border-radius: 6px;
            }}
        """)
        self.layout.addWidget(self.progress_bar)
        
        # Progress text (e.g., "3/10 文件")
        self.progress_text = QLabel("")
        self.progress_text.setStyleSheet(f"""
            font-size: 12px;
            color: {COLORS['text_light']};
            margin-top: 4px;
        """)
        self.progress_text.setAlignment(Qt.AlignRight)
        self.layout.addWidget(self.progress_text)
        
        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        self.log_output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['background']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 12px;
                color: {COLORS['text_secondary']};
            }}
        """)
        self.layout.addWidget(self.log_output)
        
        # Cancel button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondary_btn")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_btn)
        
        self.layout.addLayout(btn_layout)
    
    def _on_cancel(self) -> None:
        """Handle cancel button click"""
        self.cancel_requested.emit()
        self.cancel_btn.setEnabled(False)
        self.append_log("正在取消...")
    
    def start(self, total: int = 100) -> None:
        """Start progress tracking"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.cancel_btn.setEnabled(True)
        self.log_output.clear()
    
    def update_progress(self, current: int, total: int, status: str = "") -> None:
        """Update progress bar and status"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        
        if total > 0:
            percent = int(current / total * 100)
            self.progress_bar.setFormat(f"{percent}%")
            self.progress_text.setText(f"{current}/{total}")
        
        if status:
            self.status_label.setText(status)
    
    def set_status(self, status: str) -> None:
        """Update status text"""
        self.status_label.setText(status)
    
    def append_log(self, message: str) -> None:
        """Append message to log output"""
        self.log_output.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def finish(self, success: bool = True) -> None:
        """Mark progress as complete"""
        self.cancel_btn.setEnabled(False)
        if success:
            # 确保进度条有明确的最大值，避免无限滚动
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setFormat("100%")
            self.status_label.setText("完成")
            self.status_label.setStyleSheet(f"""
                font-size: 14px;
                color: {COLORS['success']};
                font-weight: 500;
            """)
        else:
            self.status_label.setText("已取消")
            self.status_label.setStyleSheet(f"""
                font-size: 14px;
                color: {COLORS['warning']};
            """)
    
    def reset(self) -> None:
        """Reset to initial state"""
        self.progress_bar.setValue(0)
        self.progress_text.setText("")
        self.status_label.setText("准备就绪")
        self.status_label.setStyleSheet(f"""
            font-size: 14px;
            color: {COLORS['text_secondary']};
        """)
        self.log_output.clear()
        self.cancel_btn.setEnabled(False)
