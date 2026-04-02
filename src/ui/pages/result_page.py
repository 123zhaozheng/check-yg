# -*- coding: utf-8 -*-
"""
Result page - review results display and export
"""
import shutil
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QFileDialog
)

from ..widgets import Card, ResultTable
from ..styles import COLORS
from ...config import get_config


class ResultPage(QWidget):
    """
    Result page for displaying review results
    - Match details table
    - Export functionality
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.result = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        
        # Page title
        header_layout = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title = QLabel("审查结果")
        title.setObjectName("title")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        title_layout.addWidget(title)
        
        self.subtitle = QLabel("审查完成，查看匹配结果")
        self.subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        title_layout.addWidget(self.subtitle)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Result table
        table_card = Card()
        table_card.add_title("匹配明细")
        
        self.result_table = ResultTable()
        table_card.layout.addWidget(self.result_table)
        
        layout.addWidget(table_card, 1)  # Stretch to fill
        
        # Bottom action bar
        action_layout = QHBoxLayout()
        
        action_layout.addStretch()

        self.export_btn = QPushButton("导出Excel")
        self.export_btn.setObjectName("secondary_btn")
        self.export_btn.clicked.connect(self._export_excel)
        action_layout.addWidget(self.export_btn)
        
        self.new_audit_btn = QPushButton("新建审查")
        self.new_audit_btn.setObjectName("secondary_btn")
        action_layout.addWidget(self.new_audit_btn)
        
        layout.addLayout(action_layout)
    
    def set_review_result(self, result) -> None:
        """
        设置审查结果（来自 Reviewer）
        
        Args:
            result: ReviewResult 对象
        """
        self.result = result
        
        # 转换匹配记录格式并更新表格
        matches_data = [m.to_dict() for m in result.matches]
        self.result_table.set_data(matches_data)
        
        # 更新副标题
        if result.total_matches == 0:
            self.subtitle.setText("未发现匹配记录")
        else:
            self.subtitle.setText(f"发现 {result.total_matches} 条匹配记录")
    
    def _export_excel(self) -> None:
        """Export the reviewed flow workbook with match columns written back."""
        if not self.result:
            QMessageBox.warning(self, "无数据", "没有可导出的审查结果")
            return
        
        default_name = f"审查结果_{self.result.review_id}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出审查结果",
            str(self.config.reports_folder / default_name),
            "Excel Files (*.xlsx)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        
        try:
            source_path = Path(str(self.result.flow_excel_path or "")).expanduser()
            if not source_path.exists():
                raise FileNotFoundError(f"审查后的流水文件不存在: {source_path}")

            target_path = Path(file_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            
            QMessageBox.information(
                self, "导出成功",
                "审查结果已导出到:\n"
                f"{file_path}\n\n"
                "导出文件保留了原流水表，并已写入“匹配用户/匹配度”列。"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "导出失败",
                f"导出审查结果时出错:\n{str(e)}"
            )
    
    def clear(self) -> None:
        """Clear results"""
        self.result = None
        self.result_table.clear()
