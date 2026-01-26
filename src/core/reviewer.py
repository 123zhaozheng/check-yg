# -*- coding: utf-8 -*-
"""
Reviewer - 简化版流水审查器
只做精确匹配和脱敏匹配，不调用LLM
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import openpyxl
from ..core.matcher import NameMatcher, MatchResult, MatchType
from ..core.customer import CustomerManager
from ..config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ReviewMatch:
    """审查匹配结果"""
    customer_name: str
    counterparty_name: str
    counterparty_account: str
    match_type: str  # "精确匹配" / "脱敏匹配"
    confidence: int
    source_file: str
    transaction_time: str = ""
    amount: str = ""
    summary: str = ""
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'customer_name': self.customer_name,
            'counterparty_name': self.counterparty_name,
            'counterparty_account': self.counterparty_account,
            'match_type': self.match_type,
            'confidence': self.confidence,
            'source_file': self.source_file,
            'transaction_time': self.transaction_time,
            'amount': self.amount,
            'summary': self.summary,
        }


@dataclass
class ReviewResult:
    """审查结果"""
    review_id: str
    review_time: str
    flow_excel_path: str
    customer_excel_path: str
    total_customers: int
    matched_customers: int
    total_matches: int
    total_amount: float
    matches: List[ReviewMatch] = field(default_factory=list)
    
    def __post_init__(self):
        if self.matches is None:
            self.matches = []
    
    @property
    def total_amount_formatted(self) -> str:
        """格式化总金额"""
        return f"¥{self.total_amount:,.2f}"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        from dataclasses import asdict
        result = asdict(self)
        result['matches'] = [m.to_dict() for m in self.matches]
        return result


class Reviewer:
    """
    流水审查器（简化版）
    
    只做精确匹配和脱敏匹配，不调用LLM
    """
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self.matcher = NameMatcher(fuzzy_threshold=self.config.fuzzy_threshold)
        self.customer_manager = CustomerManager()
    
    def load_flows(self, excel_path: str) -> List[dict]:
        """
        加载流水Excel
        
        Args:
            excel_path: Excel文件路径
            
        Returns:
            List[dict]: 流水记录列表
        """
        try:
            path = Path(excel_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {excel_path}")
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active

            rows_iter = ws.iter_rows(values_only=True)
            headers = []
            for row in rows_iter:
                headers = [str(cell).strip() if cell is not None else "" for cell in row]
                break

            if not any(headers):
                wb.close()
                raise ValueError("流水Excel缺少表头")

            records = []
            for row in rows_iter:
                record = {}
                for idx, header in enumerate(headers):
                    if not header:
                        continue
                    value = row[idx] if idx < len(row) else ""
                    record[header] = "" if value is None else str(value).strip()
                if record:
                    records.append(record)
            wb.close()
            logger.info("加载流水: %d 条", len(records))
            return records
        except Exception as e:
            logger.error("加载流水Excel失败: %s", e)
            raise
    
    def load_customers(self, excel_path: str) -> int:
        """
        加载客户名单
        
        Args:
            excel_path: Excel文件路径
            
        Returns:
            int: 客户数量
        """
        count = self.customer_manager.load_from_excel(excel_path)
        logger.info("加载客户: %d 个", count)
        return count
    
    def run_review(
        self,
        flow_excel_path: str,
        customer_excel_path: str = "",
        customers: Optional[List[str]] = None
    ) -> ReviewResult:
        """
        执行审查
        
        Args:
            flow_excel_path: 流水Excel路径
            customer_excel_path: 客户名单Excel路径
            
        Returns:
            ReviewResult: 审查结果
        """
        # 加载数据
        flows = self.load_flows(flow_excel_path)
        if customers is not None:
            self.customer_manager.load_from_list(customers)
            customer_count = self.customer_manager.count
        else:
            customer_count = self.load_customers(customer_excel_path)
        
        # 匹配
        matches = []
        for flow in flows:
            counterparty = str(flow.get('交易对手名', ''))
            counterparty_account = str(flow.get('交易对手账号', ''))
            if not counterparty:
                continue
            
            # 尝试匹配每个客户
            for customer in self.customer_manager:
                # 精确匹配
                if self.config.enable_exact_match:
                    result = self.matcher.match_exact(customer, counterparty)
                    if result:
                        matches.append(self._create_match(
                            customer, result, flow, counterparty, counterparty_account
                        ))
                        continue
                
                # 脱敏匹配
                if self.config.enable_desensitized_match:
                    result = self.matcher.match_desensitized(customer, counterparty)
                    if result:
                        matches.append(self._create_match(
                            customer, result, flow, counterparty, counterparty_account
                        ))
        
        # 统计
        total_amount = sum(
            float(str(flow.get('金额', '0')).replace(',', '').replace('¥', ''))
            for flow in flows
        )
        matched_customers = set(m.customer_name for m in matches)
        
        return ReviewResult(
            review_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            review_time=datetime.now().isoformat(),
            flow_excel_path=flow_excel_path,
            customer_excel_path=customer_excel_path,
            total_customers=customer_count,
            matched_customers=len(matched_customers),
            total_matches=len(matches),
            total_amount=total_amount,
            matches=matches
        )
    
    def _create_match(
        self,
        customer_name: str,
        match_result: MatchResult,
        flow: dict,
        counterparty: str,
        counterparty_account: str
    ) -> ReviewMatch:
        """创建审查匹配对象"""
        return ReviewMatch(
            customer_name=customer_name,
            counterparty_name=counterparty,
            counterparty_account=counterparty_account,
            match_type=match_result.match_type.value,
            confidence=match_result.confidence,
            source_file=str(flow.get('来源文件', '')),
            transaction_time=str(flow.get('交易时间', '')),
            amount=str(flow.get('金额', '')),
            summary=str(flow.get('摘要', '')),
        )
