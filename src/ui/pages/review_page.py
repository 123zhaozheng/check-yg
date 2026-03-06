# -*- coding: utf-8 -*-
"""
Review page - Flow review configuration UI
Upload customer list and match against flow records
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..widgets import Card, FileSelector
from ..styles import COLORS
from ...config import get_config


class ReviewPage(QWidget):
    """
    Flow review configuration page
    - Flow data summary display
    - Customer list file selection
    - Match type configuration
    - Start review action
    """
    
    start_review = pyqtSignal(str, list)  # flow_excel_path, customers
    back_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.flow_excel_path = ""
        self.customer_excel_path = ""
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("流水审查")
        title.setObjectName("title")
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)
        
        subtitle = QLabel("上传客户名单，匹配流水中的交易对手")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        layout.addWidget(subtitle)
        
        # Main content - two columns
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Left column - Flow data
        left_column = QVBoxLayout()
        left_column.setSpacing(16)
        
        flow_card = Card()
        flow_card.add_title("当前流水数据")
        
        self.flow_info_label = QLabel("暂无流水数据")
        self.flow_info_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 13px;
            padding: 8px 0;
        """)
        self.flow_info_label.setWordWrap(True)
        flow_card.layout.addWidget(self.flow_info_label)
        
        self.flow_selector = FileSelector(
            placeholder="选择流水Excel文件...",
            mode="file",
            file_filter="Excel Files (*.xlsx *.xls)"
        )
        self.flow_selector.path_changed.connect(self._on_flow_file_changed)
        flow_card.layout.addWidget(self.flow_selector)
        
        left_column.addWidget(flow_card)
        left_column.addStretch()
        
        # Right column - Customer list
        right_column = QVBoxLayout()
        right_column.setSpacing(16)
        
        customer_card = Card()
        customer_card.add_title("客户名单")
        
        desc_label = QLabel("选择包含客户姓名的 Excel 文件（第一列为姓名）")
        desc_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-bottom: 8px;")
        desc_label.setWordWrap(True)
        customer_card.layout.addWidget(desc_label)
        
        self.customer_selector = FileSelector(
            placeholder="选择客户名单Excel文件...",
            mode="file",
            file_filter="Excel Files (*.xlsx *.xls)"
        )
        self.customer_selector.path_changed.connect(self._on_customer_file_changed)
        customer_card.layout.addWidget(self.customer_selector)
        
        # Customer preview table
        self.customer_table = QTableWidget()
        self.customer_table.setColumnCount(1)
        self.customer_table.setHorizontalHeaderLabels(["客户姓名"])
        header = self.customer_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.customer_table.verticalHeader().setVisible(False)
        self.customer_table.verticalHeader().setDefaultSectionSize(36)
        self.customer_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.customer_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.customer_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.customer_table.setAlternatingRowColors(True)
        self.customer_table.setMinimumHeight(220)
        self.customer_table.setStyleSheet(f"""
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
                padding: 6px;
                border: none;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QTableWidget QLineEdit {{
                padding: 2px 6px;
                margin: 0px;
                min-height: 20px;
                color: {COLORS['text_primary']};
                background-color: {COLORS['card']};
            }}
        """)
        self.customer_table.itemChanged.connect(self._update_customer_count)
        customer_card.layout.addWidget(self.customer_table)

        # Customer table actions
        customer_actions = QHBoxLayout()
        customer_actions.setSpacing(8)

        self.add_customer_btn = QPushButton("新增一行")
        self.add_customer_btn.setObjectName("secondary_btn")
        self.add_customer_btn.setFixedHeight(32)
        self.add_customer_btn.clicked.connect(self._add_customer_row)
        customer_actions.addWidget(self.add_customer_btn)

        self.remove_customer_btn = QPushButton("删除所选")
        self.remove_customer_btn.setObjectName("secondary_btn")
        self.remove_customer_btn.setFixedHeight(32)
        self.remove_customer_btn.clicked.connect(self._remove_selected_rows)
        customer_actions.addWidget(self.remove_customer_btn)

        self.customer_count_label = QLabel("")
        self.customer_count_label.setStyleSheet(f"""
            color: {COLORS['primary']};
            font-size: 13px;
            padding: 0 0 0 8px;
        """)
        customer_actions.addWidget(self.customer_count_label)

        customer_actions.addStretch()
        customer_card.layout.addLayout(customer_actions)
        
        right_column.addWidget(customer_card)
        
        # Match type options
        match_card = Card()
        match_card.add_title("匹配选项")
        
        self.exact_check = QCheckBox("精确匹配（姓名完全一致）")
        self.exact_check.setChecked(self.config.enable_exact_match)
        self.exact_check.setStyleSheet(f"""
            QCheckBox {{
                font-size: 13px;
                color: {COLORS['text_primary']};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
        """)
        match_card.layout.addWidget(self.exact_check)
        
        self.desensitized_check = QCheckBox("脱敏匹配（张* 匹配 张三）")
        self.desensitized_check.setChecked(self.config.enable_desensitized_match)
        self.desensitized_check.setStyleSheet(f"""
            QCheckBox {{
                font-size: 13px;
                color: {COLORS['text_primary']};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
        """)
        match_card.layout.addWidget(self.desensitized_check)
        
        right_column.addWidget(match_card)
        right_column.addStretch()
        
        content_layout.addLayout(left_column, 1)
        content_layout.addLayout(right_column, 1)
        
        layout.addLayout(content_layout, 1)
        
        # Bottom action bar
        action_layout = QHBoxLayout()
        
        self.back_btn = QPushButton("←  上一步")
        self.back_btn.setObjectName("secondary_btn")
        self.back_btn.setFixedSize(100, 40)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_requested.emit)
        action_layout.addWidget(self.back_btn)
        
        action_layout.addStretch()
        
        self.start_btn = QPushButton("开始审查")
        self.start_btn.setObjectName("primary_btn")
        self.start_btn.setFixedSize(120, 40)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._start_review)
        action_layout.addWidget(self.start_btn)
        
        layout.addLayout(action_layout)
    
    def set_flow_info(self, task_id: str, record_count: int, file_path: str = "") -> None:
        """Set flow data summary"""
        self.flow_excel_path = file_path
        text = f"任务编号: {task_id}\n流水条数: {record_count}"
        if file_path:
            from pathlib import Path
            text += f"\n文件: {Path(file_path).name}"
        self.flow_info_label.setText(text)
        if file_path:
            self.flow_selector.set_path(file_path)
    
    def set_flow_excel_path(self, file_path: str) -> None:
        """
        设置流水Excel文件路径（从PreviewPage传递）
        
        Args:
            file_path: 流水Excel文件路径
        """
        self.flow_excel_path = file_path
        self.flow_selector.set_path(file_path)
        
        # 尝试读取流水数量
        try:
            from pathlib import Path
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            record_count = max(0, ws.max_row - 1)
            wb.close()
            self.flow_info_label.setText(
                f"流水条数: {record_count}\n文件: {Path(file_path).name}"
            )
        except Exception:
            from pathlib import Path
            self.flow_info_label.setText(f"文件: {Path(file_path).name}")
    
    def _on_flow_file_changed(self, path: str) -> None:
        """Handle flow file selection"""
        if path:
            self.set_flow_excel_path(path)
        else:
            self.flow_excel_path = ""
    
    def _on_customer_file_changed(self, path: str) -> None:
        """Handle customer file selection"""
        self.customer_excel_path = path
        if path:
            try:
                from ...core.customer import CustomerManager
                manager = CustomerManager()
                count = manager.load_from_excel(path)
                self._load_customers_to_table(manager.customers)
                self.customer_count_label.setText(f"已加载: {count} 个客户")
            except Exception as e:
                self.customer_count_label.setText(f"加载失败: {str(e)}")
        else:
            self.customer_count_label.setText("")
    
    def _start_review(self) -> None:
        """Validate and start review"""
        if not self.flow_excel_path:
            QMessageBox.warning(
                self, "缺少流水数据",
                "请选择流水Excel文件"
            )
            return
        
        customers = self._get_customers_from_table()
        if not customers:
            QMessageBox.warning(
                self, "缺少客户名单",
                "请导入或填写客户名单"
            )
            return
        
        # Update config
        self.config.set('matching.enable_exact', self.exact_check.isChecked())
        self.config.set('matching.enable_desensitized', self.desensitized_check.isChecked())
        self.config.save()
        
        # Emit signal
        self.start_review.emit(self.flow_excel_path, customers)
    
    def clear(self) -> None:
        """Clear page state"""
        self.flow_excel_path = ""
        self.customer_excel_path = ""
        self.flow_info_label.setText("暂无流水数据")
        self.customer_count_label.setText("")
        self.flow_selector.set_path("")
        self.customer_selector.set_path("")
        self.customer_table.setRowCount(0)

    def _load_customers_to_table(self, customers: list) -> None:
        self.customer_table.setRowCount(0)
        for name in customers:
            row = self.customer_table.rowCount()
            self.customer_table.insertRow(row)
            item = QTableWidgetItem(str(name))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.customer_table.setItem(row, 0, item)
        for row in range(self.customer_table.rowCount()):
            self.customer_table.setRowHeight(row, 36)
        self._customer_table_loaded = True

    def _get_customers_from_table(self) -> list:
        names = []
        seen = set()
        for row in range(self.customer_table.rowCount()):
            item = self.customer_table.item(row, 0)
            if not item:
                continue
            name = item.text().strip()
            if name and name not in seen:
                names.append(name)
                seen.add(name)
        return names

    def _add_customer_row(self) -> None:
        row = self.customer_table.rowCount()
        self.customer_table.insertRow(row)
        item = QTableWidgetItem("")
        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.customer_table.setItem(row, 0, item)
        self.customer_table.setRowHeight(row, 36)
        self.customer_table.setCurrentCell(row, 0)
        self._update_customer_count()

    def _remove_selected_rows(self) -> None:
        selected = self.customer_table.selectionModel().selectedRows()
        for index in sorted(selected, key=lambda x: x.row(), reverse=True):
            self.customer_table.removeRow(index.row())
        self._update_customer_count()

    def _update_customer_count(self) -> None:
        count = len(self._get_customers_from_table())
        if count > 0:
            self.customer_count_label.setText(f"当前: {count} 个客户")
        else:
            self.customer_count_label.setText("")
