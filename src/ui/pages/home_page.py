# -*- coding: utf-8 -*-
"""
Home page - Task dashboard and entry point
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QFrame, QMenu, QAction,
    QMessageBox, QDialog, QLineEdit, QFormLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QFont

from ..widgets import Card
from ..styles import COLORS
from ...core.checkpoint_manager import CheckpointManager
from ...config import get_config


class NewTaskDialog(QDialog):
    """Dialog for creating a new audit task with a title"""
    def __init__(self, existing_titles: List[str], parent=None):
        super().__init__(parent)
        self.existing_titles = existing_titles
        self.task_title = ""
        self._setup_ui()

    def _setup_ui(self):
        # Keep only close button on the title bar and hide context-help button.
        self.setWindowTitle("")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, False)
        self.setFixedSize(420, 170)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['card']};
            }}
            QLineEdit {{
                padding: 8px 10px;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                background-color: white;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['text_secondary']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 16, 20, 16)

        form = QFormLayout()
        form.setSpacing(12)
        
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("请输入任务标题（例如：2023年度审计）")
        form.addRow("任务标题:", self.title_input)
        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        button_style = f"""
            QPushButton {{
                background-color: white;
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['sidebar_hover']};
                border-color: {COLORS['text_light']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['border_light']};
            }}
        """

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(92, 34)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(button_style)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.confirm_btn = QPushButton("确定")
        self.confirm_btn.setFixedSize(92, 34)
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setStyleSheet(button_style)
        self.confirm_btn.setDefault(True)
        self.confirm_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.confirm_btn)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self):
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "输入错误", "任务标题不能为空")
            return
        if title in self.existing_titles:
            QMessageBox.warning(self, "输入错误", "任务标题已存在，请使用不同的标题")
            return
        
        self.task_title = title
        self.accept()


class TaskCard(Card):
    """Card representing a single audit task"""

    STATUS_LABELS = {
        "pending": "等待中",
        "extracting": "提取中",
        "stage1_done": "提取中",
        "normalizing": "标准化中",
        "stage2_running": "标准化中",
        "completed": "已完成",
        "canceled": "已取消",
        "failed": "失败",
    }
    ACTIVE_STATUSES = {"pending", "extracting", "stage1_done", "normalizing", "stage2_running"}

    resume_requested = pyqtSignal(str)  # task_id
    view_requested = pyqtSignal(str)    # task_id
    delete_requested = pyqtSignal(str)  # task_id

    def __init__(self, task_data: Dict, parent=None):
        super().__init__(parent, padding=16)
        self.task_id = task_data.get("task_id", "Unknown")
        self.task_title = task_data.get("title", f"任务: {self.task_id}")
        self.task_data = task_data
        self.raw_status = self._get_raw_status()
        self.display_status = self._get_display_status(self.raw_status)
        self.can_resume = self._can_resume()
        self._setup_task_ui()

    def _setup_task_ui(self):
        # Header: Icon and Status
        header = QHBoxLayout()

        # Task Icon (Placeholder for now)
        icon_label = QLabel("📊")
        icon_label.setStyleSheet("font-size: 24px;")
        header.addWidget(icon_label)

        # Task Title and Date
        title_layout = QVBoxLayout()
        id_label = QLabel(self.task_title)
        id_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['text_primary']};")
        title_layout.addWidget(id_label)

        created_at = self.task_data.get("created_at", "")
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                date_str = created_at
            date_label = QLabel(date_str)
            date_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_light']};")
            title_layout.addWidget(date_label)

        header.addLayout(title_layout, 1)

        # Status Badge
        status_label = QLabel(self.display_status)
        status_style = self._get_status_style(self.raw_status)
        status_label.setStyleSheet(f"""
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            {status_style}
        """)
        header.addWidget(status_label)

        # More Button (Quick Actions)
        self.more_btn = QPushButton("⋮")
        self.more_btn.setFixedSize(24, 24)
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COLORS['text_light']};
                font-size: 18px;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['sidebar_hover']};
                color: {COLORS['text_primary']};
            }}
        """)
        self.more_btn.clicked.connect(self._show_menu)
        header.addWidget(self.more_btn)

        self.layout.addLayout(header)

        # Details
        detail_label = QLabel(self._get_detail_text())
        detail_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']}; margin-top: 4px;")
        self.layout.addWidget(detail_label)

        # Footer Action
        footer = QHBoxLayout()
        footer.addStretch()

        action_btn = QPushButton("继续任务" if self.can_resume else "查看结果")
        action_btn.setObjectName("primary_btn" if self.can_resume else "secondary_btn")
        action_btn.setFixedSize(80, 28)
        action_btn.setCursor(Qt.PointingHandCursor)
        if self.can_resume:
            action_btn.clicked.connect(lambda: self.resume_requested.emit(self.task_id))
        else:
            action_btn.clicked.connect(lambda: self.view_requested.emit(self.task_id))

        footer.addWidget(action_btn)
        self.layout.addLayout(footer)

    def _get_raw_status(self) -> str:
        status = str(self.task_data.get("status", "pending") or "pending").strip().lower()
        return status or "pending"

    def _get_display_status(self, status: str) -> str:
        return self.STATUS_LABELS.get(status, status or "未知状态")

    def _safe_int(self, value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _get_total_documents(self) -> int:
        total_documents = self._safe_int(self.task_data.get("total_documents", 0))
        if total_documents > 0:
            return total_documents
        return len(self.task_data.get("documents", []) or [])

    def _get_detail_text(self) -> str:
        total_documents = self._get_total_documents()
        if total_documents <= 0:
            return "包含 0 个文档"

        processed_documents = min(
            self._safe_int(self.task_data.get("processed_documents", 0)),
            total_documents,
        )
        if self.raw_status in {
            "extracting", "stage1_done", "normalizing", "stage2_running", "canceled", "failed"
        } and processed_documents > 0:
            return f"已处理 {processed_documents}/{total_documents} 个文档"
        return f"包含 {total_documents} 个文档"

    def _can_resume(self) -> bool:
        resumable_documents = self._safe_int(self.task_data.get("resumable_documents", 0))
        return self.raw_status in self.ACTIVE_STATUSES or (
            resumable_documents > 0 and self.raw_status != "completed"
        )

    def _get_status_style(self, status: str) -> str:
        if status == "completed":
            return f"background-color: {COLORS['success_light']}; color: {COLORS['success']};"
        if status in {"extracting", "stage1_done", "normalizing", "stage2_running"}:
            return f"background-color: {COLORS['primary_light']}; color: {COLORS['primary']};"
        if status == "failed":
            return f"background-color: {COLORS['danger_light']}; color: {COLORS['danger']};"
        if status == "canceled":
            return f"background-color: {COLORS['warning_light']}; color: {COLORS['warning']};"
        return f"background-color: {COLORS['sidebar_hover']}; color: {COLORS['text_secondary']};"

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {COLORS['sidebar_hover']};
                color: {COLORS['primary']};
            }}
        """)

        if self.can_resume:
            resume_act = QAction("继续任务", self)
            resume_act.triggered.connect(lambda: self.resume_requested.emit(self.task_id))
            menu.addAction(resume_act)

        if self.raw_status == "completed" or not self.can_resume:
            view_act = QAction("查看详情", self)
            view_act.triggered.connect(lambda: self.view_requested.emit(self.task_id))
            menu.addAction(view_act)

        if menu.actions():
            menu.addSeparator()

        delete_act = QAction("删除记录", self)
        delete_act.triggered.connect(lambda: self.delete_requested.emit(self.task_id))
        menu.addAction(delete_act)

        menu.exec_(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))


class HomePage(QWidget):
    """Home dashboard with task history and new task entry"""
    
    new_task_requested = pyqtSignal(str, str)  # task_id, title
    resume_task_requested = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.checkpoint_manager = CheckpointManager(
            Path(os.path.expanduser("~/.check-yg/checkpoints"))
        )
        self._setup_ui()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(24)
        
        # Header Section
        header = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        welcome_label = QLabel("欢迎回来")
        welcome_label.setStyleSheet(f"font-size: 14px; color: {COLORS['text_secondary']};")
        title_layout.addWidget(welcome_label)
        
        title_label = QLabel("审计任务看板")
        title_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['text_primary']};")
        title_layout.addWidget(title_label)
        header.addLayout(title_layout)
        
        header.addStretch()
        
        # New Task Button
        self.new_task_btn = QPushButton("＋ 新建审计任务")
        self.new_task_btn.setObjectName("primary_btn")
        self.new_task_btn.setFixedSize(160, 44)
        self.new_task_btn.setCursor(Qt.PointingHandCursor)
        self.new_task_btn.clicked.connect(self._on_new_task_clicked)
        header.addWidget(self.new_task_btn)
        
        main_layout.addLayout(header)
        
        # History Section
        history_title = QLabel("历史任务")
        history_title.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {COLORS['text_primary']};")
        main_layout.addWidget(history_title)
        
        # Task List Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("background-color: transparent;")
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.task_list_layout = QVBoxLayout(self.scroll_content)
        self.task_list_layout.setContentsMargins(0, 0, 8, 0)
        self.task_list_layout.setSpacing(16)
        
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, 1)
        
        # Initial refresh
        self.refresh_tasks()

    def _clear_layout(self, layout):
        """Recursively clear layout and its sub-layouts/widgets"""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self._clear_layout(item.layout())

    def refresh_tasks(self):
        """Load and display task history"""
        # Clear existing
        self._clear_layout(self.task_list_layout)
        
        tasks = self._get_all_tasks()
        if not tasks:
            empty_label = QLabel("暂无审计任务，点击右上角新建")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"color: {COLORS['text_light']}; padding: 40px;")
            self.task_list_layout.addWidget(empty_label)
        else:
            # Grid-like layout using Flow-style wrap would be better, but QVBoxLayout with task cards is simple
            # Let's use a Grid for cards if we want multiple per row
            
            for i, task in enumerate(tasks):
                card = TaskCard(task)
                card.resume_requested.connect(self.resume_task_requested.emit)
                card.delete_requested.connect(self._delete_task)
                # card.view_requested.connect(...)
                
                # Simple implementation: 2 cards per row
                if i % 2 == 0:
                    row_layout = QHBoxLayout()
                    row_layout.setSpacing(16)
                    self.task_list_layout.addLayout(row_layout)
                
                self.task_list_layout.itemAt(self.task_list_layout.count()-1).layout().addWidget(card)
            
            # Add stretch to the last row if odd number of items
            if len(tasks) % 2 != 0:
                self.task_list_layout.itemAt(self.task_list_layout.count()-1).layout().addStretch()
        
        self.task_list_layout.addStretch()

    def _get_all_tasks(self) -> List[Dict]:
        """Fetch tasks from checkpoint manager"""
        try:
            # Use CheckpointManager's proper method to get all tasks with summaries
            tasks = self.checkpoint_manager.get_all_tasks_with_titles()
            return tasks
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to get tasks: %s", e)
            return []

    def _generate_task_id(self) -> str:
        """Generate a unique task ID in YYYYMMDD_HHMMSS format."""
        base = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = base
        suffix = 1
        existing_ids = {
            task.get("task_id", "")
            for task in self._get_all_tasks()
            if task.get("task_id")
        }
        while candidate in existing_ids:
            candidate = "{0}_{1:02d}".format(base, suffix)
            suffix += 1
        return candidate

    def _on_new_task_clicked(self):
        tasks = self._get_all_tasks()
        existing_titles = [t.get("title", "") for t in tasks if t.get("title")]
        
        dialog = NewTaskDialog(existing_titles, self)
        if dialog.exec_() == QDialog.Accepted:
            task_id = self._generate_task_id()
            try:
                self.checkpoint_manager.start_task(task_id, [], title=dialog.task_title)
                self.checkpoint_manager.update_task_status(task_id, "pending")
            except Exception as exc:
                QMessageBox.critical(self, "创建失败", f"创建任务失败：{exc}")
                return

            self.refresh_tasks()
            self.new_task_requested.emit(task_id, dialog.task_title)

    def _delete_task(self, task_id: str):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除任务 {task_id} 及其所有临时数据吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.checkpoint_manager.clear_task(task_id)
            self.refresh_tasks()
