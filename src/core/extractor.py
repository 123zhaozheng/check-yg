# -*- coding: utf-8 -*-
"""
Flow Extractor - 核心流水提取协调器
负责协调文档扫描、表格解析、AI分析、缓存管理、流水提取
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from ..parsers import PDFParser, ExcelParser, DocxParser
from ..parsers.base import FlowRecord, RawTable
from ..cache import HeaderCache
from ..llm import TableAnalyzer
from .scanner import DocumentScanner
from ..config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """流水提取结果"""
    task_id: str
    task_time: str
    document_folder: str
    total_documents: int
    processed_documents: int
    total_tables: int
    flow_tables: int
    total_records: int
    flow_records: List[FlowRecord] = field(default_factory=list)
    
    @property
    def total_amount(self) -> float:
        """计算总金额"""
        total = 0.0
        for record in self.flow_records:
            try:
                amount_str = record.amount.replace(',', '').replace('￥', '')
                amount_str = amount_str.replace('¥', '').replace('元', '')
                amount_str = amount_str.replace('+', '').replace('-', '')
                total += abs(float(amount_str))
            except (ValueError, TypeError):
                pass
        return total
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        from dataclasses import asdict
        result = asdict(self)
        result['total_amount'] = self.total_amount
        result['flow_records'] = [r.to_dict() for r in self.flow_records]
        return result


class FlowExtractor:
    """
    流水提取器（核心协调器）
    
    工作流程：
    1. 扫描文档目录
    2. 逐个解析文档，提取原始表格
    3. 对每个表格：检查缓存 → AI分析（如无缓存）→ 提取流水记录
    4. 汇总所有流水记录
    """
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self.scanner = DocumentScanner()
        self.cache = HeaderCache(cache_dir=self.config.config_dir / 'cache')
        
        # 初始化解析器
        self.pdf_parser = PDFParser(
            mineru_url=self.config.mineru_url,
            timeout=self.config.mineru_timeout
        )
        self.excel_parser = ExcelParser()
        self.docx_parser = DocxParser()
        
        # 初始化AI分析器
        self.table_analyzer = None
        if self.config.llm_api_key:
            self.table_analyzer = TableAnalyzer(
                api_url=self.config.llm_url,
                model=self.config.llm_model,
                api_key=self.config.llm_api_key,
                timeout=60,
                preview_rows=10
            )
        
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None
        self._cancel_requested = False
    
    def set_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        """设置进度回调"""
        self._progress_callback = callback
    
    def request_cancel(self) -> None:
        """请求取消"""
        self._cancel_requested = True
    
    def _report_progress(self, message: str, current: int = 0, total: int = 0) -> None:
        """报告进度"""
        if self._progress_callback:
            self._progress_callback(message, current, total)
        logger.info(message)
    
    def extract_flows(
        self,
        document_folder: str,
        task_id: Optional[str] = None,
        batch_size: int = 20
    ) -> ExtractionResult:
        """
        从文档目录中提取所有流水
        
        Args:
            document_folder: 文档目录
            task_id: 任务ID（自动生成如果为空）
            batch_size: 每批处理的行数
            
        Returns:
            ExtractionResult: 提取结果
        """
        self._cancel_requested = False
        
        # 生成任务ID
        if not task_id:
            task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 扫描文档目录
        self._report_progress(f"正在扫描文档目录: {document_folder}")
        documents = self.scanner.scan_directory(document_folder)
        self._report_progress(f"发现 {len(documents)} 个文档")
        
        # 初始化结果
        result = ExtractionResult(
            task_id=task_id,
            task_time=datetime.now().isoformat(),
            document_folder=document_folder,
            total_documents=len(documents),
            processed_documents=0,
            total_tables=0,
            flow_tables=0,
            total_records=0
        )
        
        # 逐个处理文档
        for idx, doc_path in enumerate(documents):
            if self._cancel_requested:
                self._report_progress("提取已取消")
                break
            
            self._report_progress(
                f"正在处理: {doc_path.name}",
                idx + 1, len(documents)
            )
            
            try:
                doc_records, doc_stats = self._process_document(
                    doc_path, task_id, batch_size
                )
                result.flow_records.extend(doc_records)
                result.total_tables += doc_stats['total_tables']
                result.flow_tables += doc_stats['flow_tables']
                result.processed_documents += 1
                
                if doc_records:
                    self._report_progress(
                        f"提取了 {len(doc_records)} 条流水: {doc_path.name}"
                    )
            except Exception as e:
                logger.error("处理文档失败 %s: %s", doc_path.name, e)
        
        result.total_records = len(result.flow_records)
        self._report_progress(f"提取完成: {result.total_records} 条流水")
        
        return result
    
    def _process_document(
        self,
        doc_path: Path,
        task_id: str,
        batch_size: int
    ) -> tuple:
        """
        处理单个文档，提取流水记录
        
        支持跨页表格：第一个有表头的流水表格的映射会被后续无表头表格复用
        
        Returns:
            (records: List[FlowRecord], stats: Dict)
        """
        records = []
        stats = {
            'total_tables': 0,
            'flow_tables': 0
        }
        
        # 获取解析器
        parser = self._get_parser_for_file(doc_path)
        if not parser:
            logger.warning("无解析器: %s", doc_path.name)
            return records, stats
        
        # 提取原始表格
        raw_tables = self._extract_raw_tables(doc_path, parser)
        stats['total_tables'] = len(raw_tables)
        logger.info("文档 %s 共有 %d 个表格", doc_path.name, len(raw_tables))
        
        # 文档级别的流水表头映射（用于跨页表格复用）
        # key: 列数, value: HeaderMapping
        doc_flow_mappings: Dict[int, HeaderMapping] = {}
        
        # 先检查文档级缓存
        doc_cache_key = f"{doc_path.name}#doc_mappings"
        cached_doc_mappings = self.cache.get(task_id, doc_cache_key, doc_path)
        if cached_doc_mappings:
            # 缓存格式: {列数: mapping}，这里简化处理，只缓存一个主映射
            doc_flow_mappings[cached_doc_mappings.column_mapping.amount] = cached_doc_mappings
            logger.info("加载文档级缓存映射: %s", doc_path.name)
        
        # 处理每个表格
        for table_idx, table in enumerate(raw_tables):
            if self._cancel_requested:
                break
            
            if not table.rows:
                continue
            
            col_count = len(table.rows[0]) if table.rows else 0
            logger.info("分析表格#%d: %d行 x %d列", table_idx, len(table.rows), col_count)
            
            # AI分析表格
            if not self.table_analyzer:
                logger.warning("AI不可用，跳过表格分析")
                continue
            
            mapping = self.table_analyzer.analyze_table(table)
            
            if mapping and mapping.is_flow_table:
                # 是流水表格，保存映射供后续表格复用
                doc_flow_mappings[col_count] = mapping
                stats['flow_tables'] += 1
                logger.info("表格#%d 是流水表格 (confidence=%d%%)", 
                           table_idx, mapping.confidence)
            else:
                # AI判断不是流水表格，但检查是否可以复用之前的映射
                # 条件：列数相同，且之前有成功识别的流水表格
                if col_count in doc_flow_mappings:
                    mapping = doc_flow_mappings[col_count]
                    logger.info("表格#%d 复用之前的流水映射 (列数=%d)", table_idx, col_count)
                    stats['flow_tables'] += 1
                else:
                    # 尝试找列数接近的映射（允许±1列的误差，处理OCR问题）
                    for cached_col_count, cached_mapping in doc_flow_mappings.items():
                        if abs(cached_col_count - col_count) <= 1:
                            mapping = cached_mapping
                            logger.info("表格#%d 复用相近列数的流水映射 (%d vs %d)", 
                                       table_idx, col_count, cached_col_count)
                            stats['flow_tables'] += 1
                            break
                    else:
                        logger.info("表格#%d 不是流水表格，跳过", table_idx)
                        continue
            
            # 提取流水记录
            if mapping and mapping.is_flow_table:
                table_records = self.table_analyzer.extract_rows(
                    table, mapping, str(doc_path.name), batch_size
                )
                records.extend(table_records)
                logger.info("表格#%d 提取了 %d 条流水", table_idx, len(table_records))
        
        # 保存文档级映射到缓存（取第一个有效映射）
        if doc_flow_mappings and not cached_doc_mappings:
            first_mapping = next(iter(doc_flow_mappings.values()))
            self.cache.set(task_id, doc_cache_key, first_mapping, doc_path)
            logger.info("保存文档级流水映射缓存: %s", doc_path.name)
        
        return records, stats
        
        return records, stats
    
    def _get_parser_for_file(self, file_path: Path):
        """获取文件对应的解析器"""
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            return self.pdf_parser
        elif ext == '.docx':
            return self.docx_parser
        elif ext in ('.xlsx', '.xls'):
            return self.excel_parser
        return None
    
    def _extract_raw_tables(self, file_path: Path, parser) -> List[RawTable]:
        """
        从文档中提取原始表格
        
        Args:
            file_path: 文件路径
            parser: 解析器
            
        Returns:
            List[RawTable]: 原始表格列表
        """
        try:
            # PDF: 调用HTML解析器
            if file_path.suffix.lower() == '.pdf':
                parse_result = parser.parse(file_path)
                if not parse_result.success:
                    return []
                
                # 从HTML中提取表格
                from ..parsers.html_parser import HTMLTableParser
                html_parser = HTMLTableParser()
                return html_parser.extract_raw_tables_from_html(
                    parse_result.raw_text
                )
            
            # Excel: 直接提取原始表格
            elif file_path.suffix.lower() in ('.xlsx', '.xls'):
                return parser.extract_raw_tables(file_path)
            
            # DOCX: 调用docx解析器提取原始表格
            elif file_path.suffix.lower() == '.docx':
                return parser.extract_raw_tables(file_path)
            
            # 其他格式：暂不支持
            else:
                return []
                
        except Exception as e:
            logger.error("提取原始表格失败 %s: %s", file_path.name, e)
            return []