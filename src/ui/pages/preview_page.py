# -*- coding: utf-8 -*-
"""
Preview page - Flow records preview with search, sort, and export
"""

from pathlib import Path
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont

from ..widgets import Card, StatCardRow
from ..styles import COLORS
from ...core.extractor import ExtractionResult
from ...parsers.base import FlowRecord
from ...export_flows import FlowExporter
from ...config import get_config


class FlowPreviewTable(QWidget):
    """
    Advanced table widget for flow records preview
    Features: frozen header, sorting, searching, pagination
    """
    
    COLUMNS = [
        ("来源文件", 140),
        ("原始行号", 70),
        ("交易时间", 130),
        ("交易对手名", 120),
        ("交易对手账号", 140),
        ("金额", 100),
        ("摘要", 160),
        ("收支类型", 80),
    ]
    
    MAX_PREVIEW_ROWS = 100
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_records: List[FlowRecord] = []
        self._filtered_records: List[FlowRecord] = []
        self._sort_column = -1
        self._sort_order = Qt.AscendingOrder
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(12)
        
        # Search icon and input
        search_container = QFrame()
        search_container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
            QFrame:focus-within {{
                border-color: {COLORS['primary']};
            }}
        """)
        search_container_layout = QHBoxLayout(search_container)
        search_container_layout.setContentsMargins(12, 0, 12, 0)
        search_container_layout.setSpacing(8)
        
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(f"color: {COLORS['text_light']}; font-size: 14px;")
        search_container_layout.addWidget(search_icon)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索任意列内容...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                border: none;
                padding: 10px 0;
                color: {COLORS['text_primary']};
                font-size: 13px;
            }}
        """)
        self.search_input.textChanged.connect(self._on_search)
        search_container_layout.addWidget(self.search_input, 1)
        
        # Clear button
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COLORS['text_light']};
                font-size: 12px;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['border_light']};
                color: {COLORS['text_secondary']};
            }}
        """)
        self.clear_btn.clicked.connect(self._clear_search)
        self.clear_btn.hide()
        search_container_layout.addWidget(self.clear_btn)
        
        search_layout.addWidget(search_container, 1)
        
        # Result count label
        self.count_label = QLabel("共 0 条记录")
        self.count_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 12px;
            padding: 0 8px;
        """)
        search_layout.addWidget(self.count_label)
        
        layout.addLayout(search_layout)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        
        # Configure header
        header = self.table.horizontalHeader()
        for i, (_, width) in enumerate(self.COLUMNS):
            self.table.setColumnWidth(i, width)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        
        # Table styling
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        
        self._apply_table_style()
        
        layout.addWidget(self.table, 1)
        
        # Preview limit notice
        self.limit_notice = QLabel()
        self.limit_notice.setStyleSheet(f"""
            color: {COLORS['warning']};
            font-size: 11px;
            padding: 4px 0;
        """)
        self.limit_notice.hide()
        layout.addWidget(self.limit_notice)
    
    def _apply_table_style(self) -> None:
        """Apply comprehensive table styling"""
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                gridline-color: {COLORS['border_light']};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 8px 10px;
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
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid {COLORS['border']};
                border-right: 1px solid {COLORS['border_light']};
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QHeaderView::section:hover {{
                background-color: {COLORS['sidebar_hover']};
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['border']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['text_light']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
    
    def set_records(self, records: List[FlowRecord]) -> None:
        """Set flow records data"""
        self._all_records = records
        self._filtered_records = records
        self._sort_column = -1
        self.search_input.clear()
        
        # 禁用表格更新以提高性能
        self.table.setUpdatesEnabled(False)
        try:
            self._update_table()
        finally:
            self.table.setUpdatesEnabled(True)
    
    def _update_table(self) -> None:
        """Update table with current filtered/sorted records"""
        from PyQt5.QtWidgets import QApplication
        
        records = self._filtered_records
        total_count = len(records)
        
        # Limit preview rows
        display_records = records[:self.MAX_PREVIEW_ROWS]
        display_count = len(display_records)
        
        # Update count label
        if total_count > self.MAX_PREVIEW_ROWS:
            self.count_label.setText(f"显示前 {display_count} 条 / 共 {total_count} 条")
            self.limit_notice.setText(f"⚠ 仅显示前 {self.MAX_PREVIEW_ROWS} 条记录，导出Excel可获取全部数据")
            self.limit_notice.show()
        else:
            self.count_label.setText(f"共 {total_count} 条记录")
            self.limit_notice.hide()
        
        # 清空表格
        self.table.setRowCount(0)
        
        # 批量填充表格，每50行刷新一次UI
        BATCH_SIZE = 50
        self.table.setRowCount(display_count)
        
        for row, record in enumerate(display_records):
            self._set_row_data(row, record)
            
            # 每批次处理完后让 UI 有机会响应
            if (row + 1) % BATCH_SIZE == 0:
                QApplication.processEvents()
        
        # Adjust row heights
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, 40)
    
    def _set_row_data(self, row: int, record: FlowRecord) -> None:
        """Set data for a single row"""
        import os
        filename = os.path.basename(record.source_file)
        
        data = [
            filename,
            str(record.original_row),
            record.transaction_time,
            record.counterparty_name,
            record.counterparty_account,
            record.amount,
            record.summary,
            record.transaction_type,
        ]
        
        for col, value in enumerate(data):
            item = QTableWidgetItem(str(value) if value else "")
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            
            # Color code transaction type
            if col == 7:  # 收支类型
                if "收" in str(value) or "入" in str(value):
                    item.setForeground(QBrush(QColor(COLORS['success'])))
                elif "支" in str(value) or "出" in str(value):
                    item.setForeground(QBrush(QColor(COLORS['danger'])))
            
            # Color code amount
            if col == 5:  # 金额
                item.setFont(QFont("Consolas", 11))
                amount_str = str(value)
                if amount_str.startswith('-'):
                    item.setForeground(QBrush(QColor(COLORS['danger'])))
                elif amount_str and amount_str[0].isdigit():
                    item.setForeground(QBrush(QColor(COLORS['success'])))
            
            self.table.setItem(row, col, item)
    
    def _on_search(self, text: str) -> None:
        """Handle search input"""
        text = text.strip().lower()
        
        if text:
            self.clear_btn.show()
            self._filtered_records = [
                r for r in self._all_records
                if self._record_matches(r, text)
            ]
        else:
            self.clear_btn.hide()
            self._filtered_records = self._all_records
        
        self._update_table()
    
    def _record_matches(self, record: FlowRecord, search_text: str) -> bool:
        """Check if record matches search text"""
        fields = [
            record.source_file,
            str(record.original_row),
            record.transaction_time,
            record.counterparty_name,
            record.counterparty_account,
            record.amount,
            record.summary,
            record.transaction_type,
        ]
        return any(search_text in str(f).lower() for f in fields)
    
    def _clear_search(self) -> None:
        """Clear search input"""
        self.search_input.clear()
    
    def _on_header_clicked(self, column: int) -> None:
        """Handle header click for sorting"""
        if self._sort_column == column:
            # Toggle sort order
            self._sort_order = (
                Qt.DescendingOrder 
                if self._sort_order == Qt.AscendingOrder 
                else Qt.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.AscendingOrder
        
        self._sort_records()
        self._update_table()
        self.table.horizontalHeader().setSortIndicator(column, self._sort_order)
    
    def _sort_records(self) -> None:
        """Sort filtered records by current column"""
        if self._sort_column < 0:
            return
        
        def get_sort_key(record: FlowRecord):
            fields = [
                record.source_file,
                record.original_row,
                record.transaction_time,
                record.counterparty_name,
                record.counterparty_account,
                record.amount,
                record.summary,
                record.transaction_type,
            ]
            value = fields[self._sort_column]
            
            # Handle numeric sorting for row number and amount
            if self._sort_column == 1:  # original_row
                return int(value) if value else 0
            elif self._sort_column == 5:  # amount
                try:
                    clean = str(value).replace(',', '').replace('¥', '')
                    clean = clean.replace('￥', '').replace('元', '')
                    return float(clean) if clean else 0
                except ValueError:
                    return 0
            return str(value).lower()
        
        reverse = self._sort_order == Qt.DescendingOrder
        self._filtered_records.sort(key=get_sort_key, reverse=reverse)
    
    def get_all_records(self) -> List[FlowRecord]:
        """Get all records (for export)"""
        return self._all_records
    
    def clear(self) -> None:
        """Clear table"""
        self._all_records = []
        self._filtered_records = []
        self.table.setRowCount(0)
        self.count_label.setText("共 0 条记录")
        self.limit_notice.hide()


class PreviewPage(QWidget):
    """
    Flow preview page for displaying extraction results
    - Task info display
    - Statistics cards (documents, records, total amount)
    - Searchable/sortable flow table
    - Export and audit actions
    """
    
    start_audit = pyqtSignal()  # Signal to start audit
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.result: Optional[ExtractionResult] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        # Page header
        header_layout = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        
        title = QLabel("流水预览")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        title_layout.addWidget(title)
        
        self.subtitle = QLabel("提取完成，预览流水数据")
        self.subtitle.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 14px;
        """)
        title_layout.addWidget(self.subtitle)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Task info card
        task_card = Card(padding=16)
        task_info_layout = QHBoxLayout()
        task_info_layout.setSpacing(24)
        
        # Task ID
        task_id_container = QVBoxLayout()
        task_id_label = QLabel("任务编号")
        task_id_label.setStyleSheet(f"""
            font-size: 11px;
            color: {COLORS['text_light']};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        task_id_container.addWidget(task_id_label)
        
        self.task_id_value = QLabel("--")
        self.task_id_value.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 600;
            color: {COLORS['primary']};
            font-family: Consolas, monospace;
        """)
        task_id_container.addWidget(self.task_id_value)
        task_info_layout.addLayout(task_id_container)
        
        # Extraction time
        time_container = QVBoxLayout()
        time_label = QLabel("提取时间")
        time_label.setStyleSheet(f"""
            font-size: 11px;
            color: {COLORS['text_light']};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        time_container.addWidget(time_label)
        
        self.time_value = QLabel("--")
        self.time_value.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 500;
            color: {COLORS['text_primary']};
        """)
        time_container.addWidget(self.time_value)
        task_info_layout.addLayout(time_container)
        
        # Document count
        doc_container = QVBoxLayout()
        doc_label = QLabel("文档数量")
        doc_label.setStyleSheet(f"""
            font-size: 11px;
            color: {COLORS['text_light']};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        doc_container.addWidget(doc_label)
        
        self.doc_value = QLabel("0")
        self.doc_value.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 500;
            color: {COLORS['text_primary']};
        """)
        doc_container.addWidget(self.doc_value)
        task_info_layout.addLayout(doc_container)
        
        # Table count
        table_container = QVBoxLayout()
        table_label = QLabel("表格数量")
        table_label.setStyleSheet(f"""
            font-size: 11px;
            color: {COLORS['text_light']};
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        table_container.addWidget(table_label)
        
        self.table_value = QLabel("0")
        self.table_value.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 500;
            color: {COLORS['text_primary']};
        """)
        table_container.addWidget(self.table_value)
        task_info_layout.addLayout(table_container)
        
        task_info_layout.addStretch()
        task_card.layout.addLayout(task_info_layout)
        layout.addWidget(task_card)
        
        # Statistics cards row
        self.stats_row = StatCardRow()
        self.stat_docs = self.stats_row.add_stat(
            "文档数", "0", "个文档", COLORS['primary']
        )
        self.stat_records = self.stats_row.add_stat(
            "流水条数", "0", "条记录", COLORS['success']
        )
        self.stat_amount = self.stats_row.add_stat(
            "总金额", "¥0.00", "", COLORS['warning']
        )
        layout.addWidget(self.stats_row)
        
        # Flow table card
        table_card = Card()
        table_card.add_title("流水明细")
        
        self.flow_table = FlowPreviewTable()
        table_card.layout.addWidget(self.flow_table)
        
        layout.addWidget(table_card, 1)  # Stretch to fill
        
        # Bottom action bar
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)
        
        # Info label
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"""
            color: {COLORS['text_light']};
            font-size: 12px;
        """)
        action_layout.addWidget(self.info_label)
        
        action_layout.addStretch()
        
        # Export button
        self.export_btn = QPushButton("📥  导出Excel")
        self.export_btn.setObjectName("secondary_btn")
        self.export_btn.setMinimumSize(120, 40)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._export_excel)
        action_layout.addWidget(self.export_btn)
        
        # Start audit button
        self.audit_btn = QPushButton("🔍  开始审查")
        self.audit_btn.setObjectName("primary_btn")
        self.audit_btn.setMinimumSize(120, 40)
        self.audit_btn.setCursor(Qt.PointingHandCursor)
        self.audit_btn.clicked.connect(self._on_start_audit)
        action_layout.addWidget(self.audit_btn)
        
        layout.addLayout(action_layout)

    # 添加审查请求信号
    audit_requested = pyqtSignal(str)  # 携带流水Excel路径
    
    def set_extraction_result(self, result: ExtractionResult) -> None:
        """
        设置提取结果并更新UI
        
        Args:
            result: 流水提取结果
        """
        self.result = result
        
        # 更新任务信息
        self.task_id_value.setText(result.task_id)
        
        # 格式化时间
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(result.task_time)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            time_str = result.task_time
        self.time_value.setText(time_str)
        
        # 更新文档和表格数量
        self.doc_value.setText(str(result.processed_documents))
        self.table_value.setText(f"{result.flow_tables}/{result.total_tables}")
        
        # 更新统计卡片
        self.stat_docs.update_value(str(result.processed_documents))
        self.stat_records.update_value(str(result.total_records))
        self.stat_amount.update_value(f"¥{result.total_amount:,.2f}")
        
        # 更新流水表格
        self.flow_table.set_records(result.flow_records)
        
        # 更新副标题
        self.subtitle.setText(f"已提取 {result.total_records} 条流水记录")
    
    def _export_excel(self) -> Optional[str]:
        """
        导出流水到Excel
        
        Returns:
            导出文件路径，失败返回None
        """
        # 检查是否有数据
        if not self.result or not self.result.flow_records:
            QMessageBox.warning(
                self,
                "无法导出",
                "没有流水记录可导出，请先提取流水数据。"
            )
            return None
        
        try:
            # 创建导出器并导出
            exporter = FlowExporter()
            output_path = exporter.export(
                records=self.result.flow_records,
                task_id=self.result.task_id
            )
            
            # 显示成功提示
            QMessageBox.information(
                self,
                "导出成功",
                f"流水数据已导出到:\n{output_path}"
            )
            
            return str(output_path)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "导出失败",
                f"导出流水数据时发生错误:\n{str(e)}"
            )
            return None
    
    def _on_start_audit(self) -> None:
        """
        处理开始审查按钮点击
        1. 导出流水Excel
        2. 发出审查请求信号
        """
        # 检查是否有数据
        if not self.result or not self.result.flow_records:
            QMessageBox.warning(
                self,
                "无法开始审查",
                "没有流水记录，请先提取流水数据。"
            )
            return
        
        try:
            # 导出流水Excel
            exporter = FlowExporter()
            output_path = exporter.export(
                records=self.result.flow_records,
                task_id=self.result.task_id
            )
            
            # 发出审查请求信号
            self.audit_requested.emit(str(output_path))
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "导出失败",
                f"导出流水数据时发生错误:\n{str(e)}\n\n无法开始审查。"
            )
    
    def clear(self) -> None:
        """清空页面数据"""
        self.result = None
        self.task_id_value.setText("--")
        self.time_value.setText("--")
        self.doc_value.setText("0")
        self.table_value.setText("0")
        self.stat_docs.update_value("0")
        self.stat_records.update_value("0")
        self.stat_amount.update_value("¥0.00")
        self.flow_table.clear()
        self.subtitle.setText("提取完成，预览流水数据")
