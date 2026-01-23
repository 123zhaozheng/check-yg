# -*- coding: utf-8 -*-
"""
Result page - audit results display and export
"""

from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt
from typing import Optional

from ..widgets import Card, StatCardRow, ResultTable
from ..styles import COLORS, get_risk_style
from ...core.auditor import AuditResult
from ...export import ExcelExporter
from ...config import get_config


class ResultPage(QWidget):
    """
    Result page for displaying audit results
    - Statistics overview
    - Match details table
    - Export functionality
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.result: Optional[AuditResult] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        
        # Page title
        header_layout = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title = QLabel("审计结果")
        title.setObjectName("title")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """)
        title_layout.addWidget(title)
        
        self.subtitle = QLabel("审计完成，查看匹配结果")
        self.subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        title_layout.addWidget(self.subtitle)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        # Risk level badge
        self.risk_badge = QLabel("低风险")
        self.risk_badge.setStyleSheet(f"""
            padding: 8px 16px;
            border-radius: 16px;
            font-weight: 600;
            font-size: 14px;
            {get_risk_style("低风险")}
        """)
        header_layout.addWidget(self.risk_badge)
        
        layout.addLayout(header_layout)
        
        # Stats row
        self.stats_row = StatCardRow()
        self.stat_customers = self.stats_row.add_stat("客户总数", "0")
        self.stat_matched = self.stats_row.add_stat("命中客户", "0", color=COLORS['warning'])
        self.stat_records = self.stats_row.add_stat("匹配记录", "0", color=COLORS['primary'])
        self.stat_amount = self.stats_row.add_stat("涉及金额", "¥0")
        layout.addWidget(self.stats_row)
        
        # Result table
        table_card = Card()
        table_card.add_title("匹配明细")
        
        self.result_table = ResultTable()
        self.result_table.export_requested.connect(self._export_excel)
        table_card.layout.addWidget(self.result_table)
        
        layout.addWidget(table_card, 1)  # Stretch to fill
        
        # Bottom action bar
        action_layout = QHBoxLayout()
        
        self.audit_info_label = QLabel("")
        self.audit_info_label.setStyleSheet(f"color: {COLORS['text_light']}; font-size: 12px;")
        action_layout.addWidget(self.audit_info_label)
        
        action_layout.addStretch()
        
        self.new_audit_btn = QPushButton("新建审计")
        self.new_audit_btn.setObjectName("secondary_btn")
        action_layout.addWidget(self.new_audit_btn)
        
        layout.addLayout(action_layout)
    
    def set_result(self, result: AuditResult) -> None:
        """Set and display audit result"""
        self.result = result
        
        # Update stats
        self.stat_customers.set_value(str(result.total_customers))
        self.stat_matched.set_value(str(result.matched_customers))
        self.stat_records.set_value(str(result.total_matches))
        self.stat_amount.set_value(f"¥{result.total_amount:,.2f}")
        
        # Update risk badge
        self.risk_badge.setText(result.risk_level)
        self.risk_badge.setStyleSheet(f"""
            padding: 8px 16px;
            border-radius: 16px;
            font-weight: 600;
            font-size: 14px;
            {get_risk_style(result.risk_level)}
        """)
        
        # Update table
        self.result_table.set_data(result.matches)
        
        # Update info label
        self.audit_info_label.setText(
            f"审计编号: {result.audit_id} | 审计时间: {result.audit_time}"
        )
        
        # Update subtitle based on results
        if result.total_matches == 0:
            self.subtitle.setText("未发现匹配记录")
        else:
            self.subtitle.setText(f"发现 {result.total_matches} 条匹配记录")
    
    def set_review_result(self, result) -> None:
        """
        设置审查结果（来自 Reviewer）
        
        Args:
            result: ReviewResult 对象
        """
        # 更新统计信息
        self.stat_customers.set_value(str(result.total_customers))
        self.stat_matched.set_value(str(result.matched_customers))
        self.stat_records.set_value(str(result.total_matches))
        self.stat_amount.set_value(result.total_amount_formatted)
        
        # 根据匹配数量确定风险等级
        if result.total_matches == 0:
            risk_level = "低风险"
        elif result.total_matches < 10:
            risk_level = "中风险"
        else:
            risk_level = "高风险"
        
        self.risk_badge.setText(risk_level)
        self.risk_badge.setStyleSheet(f"""
            padding: 8px 16px;
            border-radius: 16px;
            font-weight: 600;
            font-size: 14px;
            {get_risk_style(risk_level)}
        """)
        
        # 转换匹配记录格式并更新表格
        matches_data = [m.to_dict() for m in result.matches]
        self.result_table.set_data(matches_data)
        
        # 更新信息标签
        self.audit_info_label.setText(
            f"审查编号: {result.review_id} | 审查时间: {result.review_time}"
        )
        
        # 更新副标题
        if result.total_matches == 0:
            self.subtitle.setText("未发现匹配记录")
        else:
            self.subtitle.setText(f"发现 {result.total_matches} 条匹配记录")
    
    def _export_excel(self) -> None:
        """Export results to Excel"""
        if not self.result:
            QMessageBox.warning(self, "无数据", "没有可导出的审计结果")
            return
        
        # Ask for save location
        default_name = f"审计报告_{self.result.audit_id}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出审计报告",
            str(self.config.reports_folder / default_name),
            "Excel Files (*.xlsx)"
        )
        
        if not file_path:
            return
        
        try:
            exporter = ExcelExporter(Path(file_path).parent)
            output_path = exporter.export(
                self.result,
                filename=Path(file_path).name
            )
            
            QMessageBox.information(
                self, "导出成功",
                f"审计报告已导出到:\n{output_path}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "导出失败",
                f"导出审计报告时出错:\n{str(e)}"
            )
    
    def clear(self) -> None:
        """Clear results"""
        self.result = None
        self.result_table.clear()
        self.stat_customers.set_value("0")
        self.stat_matched.set_value("0")
        self.stat_records.set_value("0")
        self.stat_amount.set_value("¥0")
        self.risk_badge.setText("低风险")
        self.audit_info_label.setText("")
