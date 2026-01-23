# -*- coding: utf-8 -*-
"""
Flow Excel Exporter - 导出流水记录到Excel
"""

import logging
from pathlib import Path
from typing import List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..parsers.base import FLOW_EXCEL_COLUMNS, FlowRecord
from ..config import get_config

logger = logging.getLogger(__name__)


class FlowExporter:
    """
    流水Excel导出器
    
    导出路径：~/.check-yg/flows/
    固定列结构：来源文件、原始行号、交易时间、交易对手名、交易对手账号、金额、摘要、收支类型
    """
    
    # 样式定义
    HEADER_FILL = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    BORDER = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # 列宽度
    COLUMN_WIDTHS = {
        '来源文件': 30,
        '原始行号': 10,
        '交易时间': 20,
        '交易对手名': 20,
        '交易对手账号': 20,
        '金额': 15,
        '摘要': 30,
        '收支类型': 12,
    }
    
    def __init__(self, output_folder: Optional[Path] = None):
        """
        初始化导出器
        
        Args:
            output_folder: 输出目录，默认 ~/.check-yg/flows/
        """
        if output_folder:
            self.output_folder = Path(output_folder)
        else:
            config = get_config()
            self.output_folder = config.config_dir / 'flows'
        
        self.output_folder.mkdir(parents=True, exist_ok=True)
    
    def export(
        self,
        records: List[FlowRecord],
        task_id: str,
        filename: Optional[str] = None
    ) -> Path:
        """
        导出流水记录到Excel
        
        Args:
            records: 流水记录列表
            task_id: 任务ID
            filename: 输出文件名（自动生成如果为空）
            
        Returns:
            Path: 导出文件路径
        """
        if not records:
            logger.warning("没有流水记录可导出")
            raise ValueError("没有流水记录可导出")
        
        # 创建工作簿
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is None:
            # 创建第一个工作表
            ws = wb.create_sheet("流水明细", 0)
        ws.title = "流水明细"
        
        # 写入表头
        for col_idx, header in enumerate(FLOW_EXCEL_COLUMNS, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = self.HEADER_FILL
            cell.font = self.HEADER_FONT
            cell.border = self.BORDER
            cell.alignment = Alignment(horizontal='center')
            
            # 设置列宽
            width = self.COLUMN_WIDTHS.get(header, 15)
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        
        # 写入数据
        for row_idx, record in enumerate(records, 2):
            row_data = record.to_list()
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = self.BORDER
                cell.alignment = Alignment(vertical='center')
        
        # 冻结首行
        ws.freeze_panes = 'A2'
        
        # 生成文件名
        if not filename:
            filename = f"流水_{task_id}.xlsx"
        
        # 保存文件
        output_path = self.output_folder / filename
        wb.save(output_path)
        
        logger.info("导出流水到: %s (%d 条记录)", 
                   output_path, len(records))
        
        return output_path