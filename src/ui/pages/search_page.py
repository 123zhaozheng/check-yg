# -*- coding: utf-8 -*-
"""
Search page - audit progress display
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QInputDialog, QMessageBox, QLineEdit
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread, pyqtSlot, QMetaObject, Q_ARG
from typing import List, Optional
import queue
import threading

from ..widgets import Card, ProgressCard, StatCardRow
from ..styles import COLORS
from ...core.auditor import Auditor, AuditResult
from ...config import get_config


class AuditWorker(QThread):
    """Background worker for running audit"""
    
    progress = pyqtSignal(str, int, int)  # message, current, total
    finished = pyqtSignal(object)  # AuditResult or None
    error = pyqtSignal(str)
    password_requested = pyqtSignal(str)  # filename - 请求密码信号
    
    def __init__(self, auditor: Auditor, excel_path: str, folder_path: str):
        super().__init__()
        self.auditor = auditor
        self.excel_path = excel_path
        self.folder_path = folder_path
        self._cancelled = False
        
        # 用于线程间传递密码的队列
        self._password_queue: queue.Queue = queue.Queue()
        self._password_event = threading.Event()
    
    def run(self):
        try:
            # Set progress callback
            self.auditor.set_progress_callback(self._on_progress)
            
            # Set password callback for PDF parser
            self.auditor.pdf_parser.set_password_callback(self._on_password_request)
            
            # Run audit
            result = self.auditor.run_audit(
                self.excel_path,
                self.folder_path
            )
            
            if not self._cancelled:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
    
    def _on_progress(self, message: str, current: int, total: int):
        if not self._cancelled:
            self.progress.emit(message, current, total)
    
    def _on_password_request(self, filename: str) -> Optional[str]:
        """
        密码请求回调 - 在工作线程中调用
        
        发送信号到主线程显示弹窗，然后等待用户输入
        """
        if self._cancelled:
            return None
        
        # 清空队列和事件
        while not self._password_queue.empty():
            try:
                self._password_queue.get_nowait()
            except queue.Empty:
                break
        self._password_event.clear()
        
        # 发送信号到主线程
        self.password_requested.emit(filename)
        
        # 等待主线程返回密码
        self._password_event.wait()
        
        try:
            return self._password_queue.get_nowait()
        except queue.Empty:
            return None
    
    def provide_password(self, password: Optional[str]):
        """
        主线程调用此方法提供密码
        """
        self._password_queue.put(password)
        self._password_event.set()
    
    def cancel(self):
        self._cancelled = True
        self.auditor.request_cancel()
        # 如果正在等待密码，也要唤醒
        self._password_queue.put(None)
        self._password_event.set()


class SearchPage(QWidget):
    """
    Search/audit progress page
    Shows real-time progress of document parsing and matching
    """
    
    audit_complete = pyqtSignal(object)  # AuditResult
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.worker: Optional[AuditWorker] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        
        # Page title
        title = QLabel("审计进度")
        title.setObjectName("title")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)
        
        self.subtitle = QLabel("正在处理文档...")
        self.subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        layout.addWidget(self.subtitle)
        
        # Stats row
        self.stats_row = StatCardRow()
        self.stat_customers = self.stats_row.add_stat("客户数量", "0")
        self.stat_documents = self.stats_row.add_stat("文档数量", "0")
        self.stat_matches = self.stats_row.add_stat("匹配记录", "0", color=COLORS['primary'])
        layout.addWidget(self.stats_row)
        
        # Progress card
        self.progress_card = ProgressCard("处理进度")
        self.progress_card.cancel_requested.connect(self._on_cancel)
        layout.addWidget(self.progress_card)
        
        # Current file card
        self.current_file_card = Card()
        self.current_file_card.add_title("当前处理")
        
        self.current_file_label = QLabel("等待开始...")
        self.current_file_label.setStyleSheet(f"""
            font-size: 14px;
            color: {COLORS['text_secondary']};
            padding: 8px 0;
        """)
        self.current_file_label.setWordWrap(True)
        self.current_file_card.layout.addWidget(self.current_file_label)
        
        layout.addWidget(self.current_file_card)
        
        layout.addStretch()
    
    def start_audit(self, excel_path: str, folder_path: str, customers: List[str]) -> None:
        """Start the audit process"""
        # Reset UI
        self.progress_card.reset()
        self.progress_card.start(100)
        self.subtitle.setText("正在处理文档...")
        self.current_file_label.setText("正在初始化...")
        
        # Update customer count
        self.stat_customers.set_value(str(len(customers)))
        self.stat_documents.set_value("0")
        self.stat_matches.set_value("0")
        
        # Create auditor and worker
        auditor = Auditor(self.config)
        
        # Pre-load customers if provided
        if customers:
            for customer in customers:
                auditor.customer_manager.add_customer(customer)
        
        self.worker = AuditWorker(auditor, excel_path, folder_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.password_requested.connect(self._on_password_requested)
        self.worker.start()
    
    @pyqtSlot(str, int, int)
    def _on_progress(self, message: str, current: int, total: int) -> None:
        """Handle progress update"""
        self.progress_card.update_progress(current, total, message)
        self.progress_card.append_log(message)
        self.current_file_label.setText(message)
        
        # Update document count
        if total > 0:
            self.stat_documents.set_value(str(total))
    
    @pyqtSlot(object)
    def _on_finished(self, result: AuditResult) -> None:
        """Handle audit completion"""
        self.progress_card.finish(success=True)
        self.subtitle.setText("审计完成")
        self.current_file_label.setText("处理完成")
        
        if result:
            self.stat_matches.set_value(str(result.total_matches))
            self.audit_complete.emit(result)
    
    @pyqtSlot(str)
    def _on_error(self, error: str) -> None:
        """Handle audit error"""
        self.progress_card.finish(success=False)
        self.progress_card.append_log(f"错误: {error}")
        self.subtitle.setText("审计出错")
        self.current_file_label.setText(f"错误: {error}")
    
    def _on_cancel(self) -> None:
        """Handle cancel request"""
        if self.worker:
            self.worker.cancel()
            self.subtitle.setText("正在取消...")
    
    @pyqtSlot(str)
    def _on_password_requested(self, filename: str) -> None:
        """Handle password request from worker thread"""
        password, ok = QInputDialog.getText(
            self,
            "PDF 密码",
            f"文件 {filename} 需要密码：\n\n"
            f"（提示：密码通常是文件名开头的数字）",
            echo=QLineEdit.Password
        )
        
        if ok and password:
            self.worker.provide_password(password)
        else:
            # 用户取消
            self.worker.provide_password(None)
