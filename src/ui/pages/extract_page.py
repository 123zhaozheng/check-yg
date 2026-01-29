# -*- coding: utf-8 -*-
"""
Extract page - Flow extraction UI with progress tracking
"""

from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox,
    QApplication, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, QObject

from ..widgets import Card, FileSelector, ProgressCard, StatCardRow
from ..styles import COLORS
from ...config import get_config


class ExtractionWorker(QObject):
    """后台提取工作线程"""
    progress = pyqtSignal(str, int, int)  # message, current, total
    finished = pyqtSignal(object)  # ExtractionResult
    canceled = pyqtSignal(object)  # ExtractionResult (partial)
    error = pyqtSignal(str)  # error message
    
    def __init__(
        self,
        config,
        folder_path: str,
        task_id: str,
        batch_size: int,
        confidence_threshold: int
    ):
        super().__init__()
        self.config = config
        self.folder_path = folder_path
        self.task_id = task_id
        self.batch_size = batch_size
        self.confidence_threshold = confidence_threshold
        self._extractor = None
        self._cancelled = False
    
    def run(self):
        """执行提取任务"""
        try:
            from ...core.extractor import FlowExtractor
            
            self._extractor = FlowExtractor(self.config)
            self._extractor.set_progress_callback(self._on_progress)
            
            result = self._extractor.extract_flows(
                document_folder=self.folder_path,
                task_id=self.task_id,
                batch_size=self.batch_size,
                confidence_threshold=self.confidence_threshold
            )
            if self._cancelled:
                self.canceled.emit(result)
            else:
                self.finished.emit(result)
                
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
    
    def _on_progress(self, message: str, current: int, total: int):
        """进度回调"""
        if not self._cancelled:
            self.progress.emit(message, current, total)
    
    def cancel(self):
        """取消提取"""
        self._cancelled = True
        if self._extractor:
            self._extractor.request_cancel()


class ExtractPage(QWidget):
    """
    Flow extraction page for extracting bank statements
    - Document folder selection
    - AI configuration (rows per batch, confidence threshold)
    - Progress tracking with statistics
    - Log output
    - Cancel support
    """
    
    extraction_completed = pyqtSignal(object)  # ExtractionResult
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self._worker = None
        self._worker_thread = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("流水提取")
        title.setObjectName("title")
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)
        
        subtitle = QLabel("从PDF/Excel文档中批量提取银行流水数据")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        layout.addWidget(subtitle)
        
        # Main content - left and right sections
        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)
        
        # Left column - Configuration
        left_column = QVBoxLayout()
        left_column.setSpacing(16)
        
        # Task info card
        task_card = Card()
        task_card.add_title("任务信息")
        
        task_info_layout = QHBoxLayout()
        task_info_layout.setSpacing(12)
        
        # Task ID
        task_id_label = QLabel("任务编号：")
        task_id_label.setStyleSheet(f"""
            font-size: 13px;
            color: {COLORS['text_secondary']};
            font-weight: 500;
        """)
        task_info_layout.addWidget(task_id_label)
        
        self.task_id_display = QLabel(self._generate_task_id())
        self.task_id_display.setStyleSheet(f"""
            font-size: 13px;
            color: {COLORS['primary']};
            font-weight: 600;
            font-family: Consolas, monospace;
        """)
        task_info_layout.addWidget(self.task_id_display)
        task_info_layout.addStretch()
        
        task_card.layout.addLayout(task_info_layout)
        left_column.addWidget(task_card)
        
        # Document folder card
        folder_card = Card()
        folder_card.add_title("文档目录")
        
        folder_desc = QLabel("选择包含银行流水PDF/Excel文档的目录")
        folder_desc.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; margin-bottom: 8px;")
        folder_desc.setWordWrap(True)
        folder_card.layout.addWidget(folder_desc)
        
        self.folder_selector = FileSelector(
            placeholder="选择文档目录...",
            mode="folder"
        )
        self.folder_selector.path_changed.connect(self._on_folder_changed)
        folder_card.layout.addWidget(self.folder_selector)
        
        # Supported formats hint
        formats_label = QLabel("支持格式: PDF, XLSX, XLS")
        formats_label.setStyleSheet(f"color: {COLORS['text_light']}; font-size: 11px; margin-top: 4px;")
        folder_card.layout.addWidget(formats_label)
        
        left_column.addWidget(folder_card)
        
        left_column.addStretch()
        
        content_layout.addLayout(left_column, 1)
        
        # Right column - Progress and stats
        right_column = QVBoxLayout()
        right_column.setSpacing(16)
        
        # Statistics cards row
        stats_row = StatCardRow()
        stats_row.add_stat("文档数", "0", "个", COLORS['primary'])
        stats_row.add_stat("已处理", "0", "个", COLORS['text_primary'])
        stats_row.add_stat("流水条数", "0", "条", COLORS['success'])
        self.stats_row = stats_row
        right_column.addWidget(stats_row)
        
        # Current file indicator
        current_file_card = Card(padding=12)
        current_file_label = QLabel("当前处理")
        current_file_label.setStyleSheet(f"""
            font-size: 12px;
            color: {COLORS['text_secondary']};
            font-weight: 500;
        """)
        current_file_card.layout.addWidget(current_file_label)
        
        self.current_file_display = QLabel("未开始")
        self.current_file_display.setStyleSheet(f"""
            font-size: 13px;
            color: {COLORS['text_primary']};
            font-weight: 500;
        """)
        self.current_file_display.setWordWrap(True)
        current_file_card.layout.addWidget(self.current_file_display)
        right_column.addWidget(current_file_card)
        
        # Progress card
        self.progress_card = ProgressCard(title="提取进度")
        self.progress_card.cancel_requested.connect(self._on_cancel)
        self.progress_card.setMinimumHeight(240)
        self.progress_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_column.addWidget(self.progress_card, 1)
        
        content_layout.addLayout(right_column, 1)
        
        layout.addLayout(content_layout, 1)
        
        # Bottom action bar
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        
        self.start_btn = QPushButton("开始提取")
        self.start_btn.setObjectName("primary_btn")
        self.start_btn.setFixedSize(120, 40)
        self.start_btn.clicked.connect(self._start_extraction)
        action_layout.addWidget(self.start_btn)
        
        layout.addLayout(action_layout)
    
    def _generate_task_id(self) -> str:
        """Generate task ID in YYYYMMDD_HHMMSS format"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _start_extraction(self) -> None:
        """Validate and start extraction"""
        folder_path = self.folder_selector.get_path()
        
        if not folder_path:
            QMessageBox.warning(
                self, "缺少文档目录",
                "请选择待提取的文档目录"
            )
            return
        
        rows = int(self.config.flow_batch_size)
        threshold = int(self.config.flow_confidence_threshold)
        
        # Update task ID
        self.task_id_display.setText(self._generate_task_id())
        
        # Disable start button
        self.start_btn.setEnabled(False)
        
        # Start extraction
        self._start_extraction_process(folder_path, rows, threshold)
    
    def _start_extraction_process(self, folder_path: str, rows: int, threshold: int) -> None:
        """Start extraction process in background thread"""
        # Update progress card
        self.progress_card.reset()
        self.progress_card.start()
        self.progress_card.set_status("正在初始化...")
        self.progress_card.append_log(f"任务编号: {self.task_id_display.text()}")
        self.progress_card.append_log(f"文档目录: {folder_path}")
        self.progress_card.append_log(f"配置: 行数={rows}, 阈值={threshold}")
        
        # Reset stats
        card0 = self.stats_row.get_card(0)
        card1 = self.stats_row.get_card(1)
        card2 = self.stats_row.get_card(2)
        if card0: card0.set_value("0")
        if card1: card1.set_value("0")
        if card2: card2.set_value("0")
        self.current_file_display.setText("准备中...")
        
        # 创建后台线程
        self._worker_thread = QThread()
        self._worker = ExtractionWorker(
            config=self.config,
            folder_path=folder_path,
            task_id=self.task_id_display.text(),
            batch_size=rows,
            confidence_threshold=threshold
        )
        self._worker.moveToThread(self._worker_thread)
        
        # 连接信号
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_extraction_finished)
        self._worker.canceled.connect(self._on_extraction_canceled)
        self._worker.error.connect(self._on_extraction_error)
        
        # 启动线程
        self._worker_thread.start()
    
    def _on_extraction_finished(self, result) -> None:
        """处理提取完成"""
        # 清理线程
        self._cleanup_worker()
        
        # Update final stats
        card0 = self.stats_row.get_card(0)
        card1 = self.stats_row.get_card(1)
        card2 = self.stats_row.get_card(2)
        if card0: card0.set_value(str(result.total_documents))
        if card1: card1.set_value(str(result.processed_documents))
        if card2: card2.set_value(str(result.total_records))
        
        # Finish progress
        self.progress_card.finish(success=True)
        self.current_file_display.setText("完成")
        self.progress_card.append_log(f"\n提取完成!")
        self.progress_card.append_log(f"总文档: {result.processed_documents}/{result.total_documents}")
        self.progress_card.append_log(f"流水表格: {result.flow_tables}/{result.total_tables}")
        self.progress_card.append_log(f"流水记录: {result.total_records} 条")
        self.progress_card.append_log(f"总金额: ¥{result.total_amount:,.2f}")
        
        # Re-enable start button
        self.start_btn.setEnabled(True)
        
        # 让 UI 有时间刷新，然后再发送信号
        QApplication.processEvents()
        QTimer.singleShot(100, lambda: self.extraction_completed.emit(result))
    
    def _on_extraction_error(self, error_msg: str) -> None:
        """处理提取错误"""
        # 清理线程
        self._cleanup_worker()
        
        self.progress_card.finish(success=False)
        self.current_file_display.setText("错误")
        self.progress_card.append_log(f"\n提取失败: {error_msg}")
        self.start_btn.setEnabled(True)
        
        QMessageBox.critical(
            self, "提取失败",
            f"流水提取过程中发生错误:\n{error_msg}"
        )
    
    def _cleanup_worker(self) -> None:
        """清理工作线程"""
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait(3000)  # 等待最多3秒
            self._worker_thread = None
        self._worker = None
    
    def _on_progress(self, message: str, current: int, total: int) -> None:
        """Handle progress updates"""
        # Update progress card
        self.progress_card.set_status(message)
        self.progress_card.append_log(message)
        
        # Update current file display
        if "正在处理:" in message:
            filename = message.split("正在处理:")[-1].strip()
            self.current_file_display.setText(filename)
        elif "正在标准化:" in message:
            filename = message.split("正在标准化:")[-1].strip()
            self.current_file_display.setText(filename)
        
        if "阶段1/2 已发现" in message and total > 0:
            card0 = self.stats_row.get_card(0)
            if card0:
                card0.set_value(str(total))
        
        if "阶段1/2" in message and total > 0 and "阶段2/2" not in message:
            card1 = self.stats_row.get_card(1)
            if card1:
                card1.set_value(str(current))
        
        # Update progress bar
        if total > 0:
            self.progress_card.update_progress(current, total)
        
        # Update progress bar
        if total > 0:
            self.progress_card.update_progress(current, total)
    
    def _on_cancel(self) -> None:
        """Handle cancel request"""
        if self._worker:
            self._worker.cancel()
        self.current_file_display.setText("正在取消...")
        self.progress_card.set_status("正在取消...")

    def _on_extraction_canceled(self, result) -> None:
        """Handle extraction canceled"""
        self._cleanup_worker()
        self.progress_card.finish(success=False)
        self.current_file_display.setText("已取消")
        self.progress_card.append_log("\n提取已取消")
        self.start_btn.setEnabled(True)

    def _on_folder_changed(self, path: str) -> None:
        """Update document count after folder selection"""
        if not path:
            return
        try:
            from ...core.scanner import DocumentScanner
            scanner = DocumentScanner()
            documents = scanner.scan_directory(path)
            card0 = self.stats_row.get_card(0)
            if card0:
                card0.set_value(str(len(documents)))
        except Exception:
            pass
    
    def get_config(self) -> dict:
        """Get current extraction configuration"""
        rows = int(self.config.flow_batch_size)
        threshold = int(self.config.flow_confidence_threshold)
        return {
            'rows': rows,
            'threshold': threshold,
            'folder': self.folder_selector.get_path()
        }
