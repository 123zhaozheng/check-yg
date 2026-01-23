# -*- coding: utf-8 -*-
"""
Configuration page - file selection and customer list management
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QSplitter
)
from PyQt5.QtCore import pyqtSignal, Qt

from ..widgets import Card, FileSelector, CustomerListWidget
from ..styles import COLORS
from ...config import get_config


class ConfigPage(QWidget):
    """
    Configuration page for setting up audit parameters
    - Customer Excel file selection
    - Document folder selection
    - Customer list preview and editing
    """
    
    start_audit = pyqtSignal(str, str, list)  # excel_path, folder_path, customers
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("审计配置")
        title.setObjectName("title")
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)
        
        subtitle = QLabel("选择客户名单和待审计文档目录")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        layout.addWidget(subtitle)
        
        # Main content - two columns
        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)
        
        # Left column - File selection
        left_column = QVBoxLayout()
        left_column.setSpacing(16)
        
        # Customer file card
        customer_card = Card()
        customer_card.add_title("客户名单")
        
        desc_label = QLabel("选择包含客户姓名的 Excel 文件（第一列为姓名）")
        desc_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-bottom: 8px;")
        desc_label.setWordWrap(True)
        customer_card.layout.addWidget(desc_label)
        
        self.customer_file_selector = FileSelector(
            placeholder="选择客户名单 Excel 文件...",
            mode="file",
            file_filter="Excel Files (*.xlsx *.xls)"
        )
        self.customer_file_selector.path_changed.connect(self._on_customer_file_changed)
        customer_card.layout.addWidget(self.customer_file_selector)
        left_column.addWidget(customer_card)
        
        # Document folder card
        folder_card = Card()
        folder_card.add_title("文档目录")
        
        folder_desc = QLabel("选择包含银行流水、交易明细等文档的目录")
        folder_desc.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-bottom: 8px;")
        folder_desc.setWordWrap(True)
        folder_card.layout.addWidget(folder_desc)
        
        self.folder_selector = FileSelector(
            placeholder="选择文档目录...",
            mode="folder"
        )
        folder_card.layout.addWidget(self.folder_selector)
        
        # Supported formats hint
        formats_label = QLabel("支持格式: PDF, DOCX, XLSX, XLS")
        formats_label.setStyleSheet(f"color: {COLORS['text_light']}; font-size: 11px; margin-top: 4px;")
        folder_card.layout.addWidget(formats_label)
        
        left_column.addWidget(folder_card)
        left_column.addStretch()
        
        content_layout.addLayout(left_column, 1)
        
        # Right column - Customer list preview
        right_column = QVBoxLayout()
        
        customer_list_card = Card()
        customer_list_card.add_title("客户名单预览")
        
        list_desc = QLabel("可手动添加或删除客户姓名")
        list_desc.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-bottom: 8px;")
        customer_list_card.layout.addWidget(list_desc)
        
        self.customer_list = CustomerListWidget()
        customer_list_card.layout.addWidget(self.customer_list)
        
        right_column.addWidget(customer_list_card)
        
        content_layout.addLayout(right_column, 1)
        
        layout.addLayout(content_layout, 1)
        
        # Bottom action bar
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        
        self.start_btn = QPushButton("开始审计")
        self.start_btn.setObjectName("primary_btn")
        self.start_btn.setFixedSize(120, 40)
        self.start_btn.clicked.connect(self._start_audit)
        action_layout.addWidget(self.start_btn)
        
        layout.addLayout(action_layout)
    
    def _on_customer_file_changed(self, path: str) -> None:
        """Handle customer file selection"""
        if not path:
            return
        
        try:
            from ...core.customer import CustomerManager
            manager = CustomerManager()
            count = manager.load_from_excel(path)
            self.customer_list.set_customers(manager.customers)
            QMessageBox.information(
                self, "导入成功", 
                f"成功导入 {count} 个客户姓名"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "导入失败",
                f"无法读取客户名单: {str(e)}"
            )
    
    def _start_audit(self) -> None:
        """Validate and start audit"""
        excel_path = self.customer_file_selector.get_path()
        folder_path = self.folder_selector.get_path()
        customers = self.customer_list.get_customers()
        
        if not excel_path and not customers:
            QMessageBox.warning(
                self, "缺少客户名单",
                "请选择客户名单 Excel 文件或手动添加客户"
            )
            return
        
        if not folder_path:
            QMessageBox.warning(
                self, "缺少文档目录",
                "请选择待审计的文档目录"
            )
            return
        
        if not customers:
            QMessageBox.warning(
                self, "客户名单为空",
                "客户名单中没有任何客户，请检查"
            )
            return
        
        # Emit signal to start audit
        self.start_audit.emit(excel_path, folder_path, customers)
    
    def get_customers(self) -> list:
        """Get current customer list"""
        return self.customer_list.get_customers()
