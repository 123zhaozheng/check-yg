# -*- coding: utf-8 -*-
"""
Main auditor module - orchestrates the audit workflow
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import get_config
from ..parsers import PDFParser, DocxParser, ExcelParser, ParseResult
from ..llm.judge import LLMJudge, VerifyResult
from .customer import CustomerManager
from .matcher import NameMatcher, MatchResult, MatchType
from .scanner import DocumentScanner

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classification"""
    HIGH = "高风险"
    MEDIUM = "中风险"
    LOW = "低风险"


@dataclass
class CandidateMatch:
    """
    候选匹配记录 - 初步匹配阶段使用
    
    轻量级数据结构，只保存必要信息，不包含交易详情。
    用于在初步匹配阶段收集候选，后续由 LLM 统一验证和提取。
    """
    raw_text: str           # 原始行文本（完整保留，不做任何修改）
    customer_name: str      # 待匹配的客户名
    source_file: str        # 来源文件路径
    row_index: int          # 行索引
    match_type: str = ""    # 初步匹配类型（精确匹配/脱敏匹配/模糊匹配）


@dataclass
class AuditMatch:
    """Single audit match record"""
    customer_name: str
    matched_text: str
    confidence: str
    confidence_score: int
    source_file: str
    row_index: int
    transaction_time: str = ""
    amount: str = ""
    transaction_type: str = ""
    summary: str = ""
    raw_text: str = ""
    ai_confirmed: Optional[bool] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditResult:
    """Complete audit result"""
    audit_id: str
    audit_time: str
    customer_file: str
    document_folder: str
    total_customers: int
    matched_customers: int
    total_matches: int
    total_amount: float
    matches: List[AuditMatch] = field(default_factory=list)
    risk_level: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['matches'] = [m.to_dict() for m in self.matches]
        return result
    
    def save(self, file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, file_path: Path) -> 'AuditResult':
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        matches = [AuditMatch(**m) for m in data.pop('matches', [])]
        return cls(**data, matches=matches)


class Auditor:
    """
    Main auditor class that orchestrates the audit workflow
    
    Workflow:
    1. Load customer names from Excel
    2. Scan document directory
    3. Parse each document
    4. Match customer names in parsed content
    5. Use LLM to extract structured transaction info
    6. Generate audit result
    """
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self.customer_manager = CustomerManager()
        self.scanner = DocumentScanner()
        self.matcher = NameMatcher(fuzzy_threshold=self.config.fuzzy_threshold)
        
        # Initialize parsers
        self.pdf_parser = PDFParser(
            mineru_url=self.config.mineru_url,
            timeout=self.config.mineru_timeout
        )
        self.docx_parser = DocxParser()
        self.excel_parser = ExcelParser()
        
        # Initialize LLM judge
        self.llm_judge: Optional[LLMJudge] = None
        if self.config.llm_api_key:
            self.llm_judge = LLMJudge(
                api_url=self.config.llm_url,
                model=self.config.llm_model,
                api_key=self.config.llm_api_key,
                batch_size=self.config.llm_batch_size,
                custom_system_prompt=self.config.llm_system_prompt
            )
        
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None
        self._cancel_requested = False
    
    def set_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        self._progress_callback = callback
    
    def request_cancel(self) -> None:
        self._cancel_requested = True
    
    def _report_progress(self, message: str, current: int = 0, total: int = 0) -> None:
        if self._progress_callback:
            self._progress_callback(message, current, total)
        logger.info(message)
    
    def load_customers(self, excel_path: str) -> int:
        self.customer_manager.clear()
        return self.customer_manager.load_from_excel(excel_path)
    
    def get_parser_for_file(self, file_path: Path):
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            return self.pdf_parser
        elif ext == '.docx':
            return self.docx_parser
        elif ext in ('.xlsx', '.xls'):
            return self.excel_parser
        return None
    
    def run_audit(self, customer_excel: str, document_folder: str) -> AuditResult:
        """
        Run complete audit workflow
        
        重构后的工作流程：
        1. 加载客户名单
        2. 扫描文档目录
        3. 解析文档并收集候选匹配（CandidateMatch）
        4. 批量调用 LLM 统一验证和提取交易信息
        5. 生成审计结果
        """
        self._cancel_requested = False
        audit_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Reload LLM judge with latest config
        self.config = get_config()
        if self.config.llm_api_key:
            self.llm_judge = LLMJudge(
                api_url=self.config.llm_url,
                model=self.config.llm_model,
                api_key=self.config.llm_api_key,
                batch_size=self.config.llm_batch_size,
                custom_system_prompt=self.config.llm_system_prompt
            )
            self._report_progress(f"AI服务已连接: {self.config.llm_model}")
        else:
            self._report_progress("警告: 未配置LLM API Key，将使用降级模式")
            self.llm_judge = None
        
        # Step 1: Load customers
        self._report_progress("正在加载客户名单...")
        customer_count = self.customer_manager.count
        if customer_count == 0 and customer_excel:
            customer_count = self.load_customers(customer_excel)
        self._report_progress(f"已加载 {customer_count} 个客户")
        
        # Step 2: Scan documents
        self._report_progress("正在扫描文档目录...")
        documents = self.scanner.scan_directory(document_folder)
        self._report_progress(f"发现 {len(documents)} 个待处理文档")
        
        # Step 3: Parse documents and collect all candidates
        all_candidates: List[CandidateMatch] = []
        
        for idx, doc_path in enumerate(documents):
            if self._cancel_requested:
                self._report_progress("审计已取消")
                break
            
            self._report_progress(f"正在处理: {doc_path.name}", idx + 1, len(documents))
            
            parser = self.get_parser_for_file(doc_path)
            if not parser:
                logger.warning("No parser for file: %s", doc_path.name)
                continue
            
            try:
                # PDF 文件需要调用 MinerU 服务
                if doc_path.suffix.lower() == '.pdf':
                    self._report_progress(f"正在请求MinerU解析: {doc_path.name}")
                
                parse_result = parser.parse(doc_path)
                
                if not parse_result.success:
                    logger.error("Failed to parse %s: %s", doc_path.name, parse_result.error_message)
                    self._report_progress(f"解析失败: {doc_path.name} - {parse_result.error_message}")
                    continue
                
                # PDF 解析成功日志
                if doc_path.suffix.lower() == '.pdf':
                    self._report_progress(f"MinerU解析成功: {doc_path.name}")
                
                # 收集候选匹配
                doc_candidates = self._collect_candidates(parse_result)
                if doc_candidates:
                    self._report_progress(f"发现 {len(doc_candidates)} 个候选匹配: {doc_path.name}")
                    all_candidates.extend(doc_candidates)
                    
            except Exception as e:
                logger.error("Error processing %s: %s", doc_path.name, e)
                self._report_progress(f"处理出错: {doc_path.name}")
        
        # Step 4: Batch verify candidates with LLM
        all_matches: List[AuditMatch] = []
        if all_candidates:
            self._report_progress(f"正在验证 {len(all_candidates)} 个候选匹配...")
            all_matches = self._verify_candidates(all_candidates)
            self._report_progress(f"验证完成: {len(all_matches)}/{len(all_candidates)} 个匹配通过")
        
        # Collect matched customers
        matched_customers = set()
        for match in all_matches:
            matched_customers.add(match.customer_name)
        
        # Calculate statistics
        total_amount = self._calculate_total_amount(all_matches)
        risk_level = self._calculate_risk_level(len(matched_customers), len(all_matches), total_amount)
        
        result = AuditResult(
            audit_id=audit_id,
            audit_time=datetime.now().isoformat(),
            customer_file=customer_excel,
            document_folder=document_folder,
            total_customers=customer_count,
            matched_customers=len(matched_customers),
            total_matches=len(all_matches),
            total_amount=total_amount,
            matches=all_matches,
            risk_level=risk_level.value
        )
        
        result_file = self.config.config_dir / f'audit_{audit_id}.json'
        result.save(result_file)
        self._report_progress(f"审计完成，结果已保存: audit_{audit_id}.json")
        
        return result
    
    def _match_in_document(self, parse_result: ParseResult) -> List[AuditMatch]:
        """Match all customers in a parsed document (保留兼容)"""
        exact_candidates, fuzzy_candidates = self._match_in_document_separated(parse_result)
        all_candidates = exact_candidates + fuzzy_candidates
        
        # 转换 CandidateMatch 为 AuditMatch（兼容旧接口）
        matches = []
        for candidate in all_candidates:
            match = AuditMatch(
                customer_name=candidate.customer_name,
                matched_text=candidate.raw_text,  # 使用原始文本
                confidence=candidate.match_type,
                confidence_score=100 if candidate.match_type == '精确匹配' else 90,
                source_file=candidate.source_file,
                row_index=candidate.row_index,
                raw_text=candidate.raw_text
            )
            matches.append(match)
        return matches
    
    def _match_in_document_separated(self, parse_result: ParseResult) -> Tuple[List[CandidateMatch], List[CandidateMatch]]:
        """
        Match all customers in a parsed document
        返回: (精确+脱敏匹配候选列表, 模糊匹配候选列表)
        
        重构后只收集 CandidateMatch，不创建完整的 AuditMatch 对象。
        后续由 LLM 统一验证和提取交易信息。
        """
        exact_matches: List[CandidateMatch] = []
        fuzzy_matches: List[CandidateMatch] = []
        
        for table in parse_result.tables:
            for row in table.rows:
                text_to_search = row.raw_text
                if row.counterparty:
                    text_to_search += " " + row.counterparty
                
                for customer in self.customer_manager:
                    # 先尝试精确匹配
                    match_result = self.matcher.match_exact(customer, text_to_search)
                    if match_result:
                        candidate = CandidateMatch(
                            raw_text=row.raw_text,
                            customer_name=customer,
                            source_file=str(parse_result.file_path),
                            row_index=row.row_index,
                            match_type=match_result.match_type.value
                        )
                        exact_matches.append(candidate)
                        continue
                    
                    # 再尝试脱敏匹配
                    match_result = self.matcher.match_desensitized(customer, text_to_search)
                    if match_result:
                        candidate = CandidateMatch(
                            raw_text=row.raw_text,
                            customer_name=customer,
                            source_file=str(parse_result.file_path),
                            row_index=row.row_index,
                            match_type=match_result.match_type.value
                        )
                        exact_matches.append(candidate)
                        continue
                    
                    # 最后尝试模糊匹配
                    match_result = self.matcher.match_fuzzy(customer, text_to_search)
                    if match_result:
                        candidate = CandidateMatch(
                            raw_text=row.raw_text,
                            customer_name=customer,
                            source_file=str(parse_result.file_path),
                            row_index=row.row_index,
                            match_type=match_result.match_type.value
                        )
                        fuzzy_matches.append(candidate)
        
        # Also search in raw text for documents without clear table structure
        if not exact_matches and not fuzzy_matches and parse_result.raw_text:
            lines = parse_result.raw_text.split('\n')
            for line_idx, line in enumerate(lines):
                if not line.strip():
                    continue
                for customer in self.customer_manager:
                    match_result = self.matcher.match_exact(customer, line)
                    if match_result:
                        candidate = CandidateMatch(
                            raw_text=line.strip(),
                            customer_name=customer,
                            source_file=str(parse_result.file_path),
                            row_index=line_idx,
                            match_type=match_result.match_type.value
                        )
                        exact_matches.append(candidate)
        
        return exact_matches, fuzzy_matches
    
    def _collect_candidates(self, parse_result: ParseResult) -> List[CandidateMatch]:
        """
        从 ParseResult 收集所有候选匹配
        
        合并精确匹配、脱敏匹配和模糊匹配的候选，
        并进行去重处理（同一行只保留优先级最高的匹配类型）。
        
        Args:
            parse_result: 文档解析结果
            
        Returns:
            List[CandidateMatch]: 去重后的候选匹配列表
        """
        exact_candidates, fuzzy_candidates = self._match_in_document_separated(parse_result)
        
        # 模糊匹配去重：排除已被精确/脱敏匹配的行
        exact_keys = {(c.source_file, c.row_index, c.customer_name) for c in exact_candidates}
        filtered_fuzzy = [
            c for c in fuzzy_candidates 
            if (c.source_file, c.row_index, c.customer_name) not in exact_keys
        ]
        
        return exact_candidates + filtered_fuzzy
    
    def _verify_candidates(self, candidates: List[CandidateMatch]) -> List[AuditMatch]:
        """
        调用 LLM 验证候选匹配并创建 AuditMatch 对象
        
        使用 LLMJudge.verify_and_extract_batch 批量验证候选匹配，
        根据置信度阈值过滤结果，并创建完整的 AuditMatch 对象。
        
        当批量调用失败时，会尝试单条处理作为回退。
        当 LLM 完全不可用时，使用降级处理。
        
        Args:
            candidates: 候选匹配列表
            
        Returns:
            List[AuditMatch]: 验证通过的审计匹配列表
        """
        if not candidates:
            return []
        
        if not self.llm_judge:
            # LLM 不可用，使用降级处理
            return self._handle_llm_unavailable(candidates)
        
        # 获取置信度阈值
        threshold = self.config.llm_match_threshold
        
        # 批量调用 LLM 验证
        try:
            verify_results = self.llm_judge.verify_and_extract_batch(candidates)
        except Exception as e:
            logger.error("LLM batch verify failed: %s", e)
            # 批量失败，尝试单条处理回退
            self._report_progress("批量验证失败，尝试单条处理...")
            verify_results = self._fallback_individual_verify(candidates)
        
        # 根据置信度阈值过滤结果并创建 AuditMatch
        matches: List[AuditMatch] = []
        for candidate, result in zip(candidates, verify_results):
            if result.confidence >= threshold:
                # 置信度达到阈值，视为匹配
                matched_text = result.matched_text if result.matched_text else candidate.raw_text
                
                # 使用 LLM 返回的置信度作为 confidence_score
                confidence_score = result.confidence
                
                match = AuditMatch(
                    customer_name=candidate.customer_name,
                    matched_text=matched_text,
                    confidence=candidate.match_type,
                    confidence_score=confidence_score,
                    source_file=candidate.source_file,
                    row_index=candidate.row_index,
                    transaction_time=result.transaction_time,
                    amount=result.amount,
                    transaction_type=result.transaction_type,
                    summary=result.summary,
                    raw_text=candidate.raw_text,
                    ai_confirmed=True
                )
                matches.append(match)
                logger.info("LLM confirmed match (confidence=%d%%): %s - %s", 
                           result.confidence, candidate.customer_name, result.reason)
            else:
                # 置信度低于阈值，记录日志
                logger.info("LLM rejected match (confidence=%d%% < %d%%): %s - %s", 
                           result.confidence, threshold, candidate.customer_name, result.reason)
        
        return matches
    
    def _handle_llm_unavailable(self, candidates: List[CandidateMatch]) -> List[AuditMatch]:
        """
        LLM 不可用时的降级处理
        
        精确匹配和脱敏匹配直接通过，模糊匹配根据配置决定是否通过。
        
        Args:
            candidates: 候选匹配列表
            
        Returns:
            List[AuditMatch]: 降级处理后的审计匹配列表
        """
        matches: List[AuditMatch] = []
        for candidate in candidates:
            if candidate.match_type in ['精确匹配', '脱敏匹配']:
                # 精确/脱敏匹配直接通过
                confidence_score = 100 if candidate.match_type == '精确匹配' else 90
                match = AuditMatch(
                    customer_name=candidate.customer_name,
                    matched_text=candidate.raw_text,  # 使用原始文本
                    confidence=candidate.match_type,
                    confidence_score=confidence_score,
                    source_file=candidate.source_file,
                    row_index=candidate.row_index,
                    raw_text=candidate.raw_text
                )
                matches.append(match)
            elif not self.config.enable_llm_judge:
                # 模糊匹配且未启用 LLM 判断，直接通过
                match = AuditMatch(
                    customer_name=candidate.customer_name,
                    matched_text=candidate.raw_text,
                    confidence=candidate.match_type,
                    confidence_score=70,
                    source_file=candidate.source_file,
                    row_index=candidate.row_index,
                    raw_text=candidate.raw_text
                )
                matches.append(match)
            else:
                # 模糊匹配需要 LLM 确认，但 LLM 不可用，跳过
                logger.warning("Skipping fuzzy match due to LLM unavailable: %s", 
                              candidate.customer_name)
        return matches
    
    def _fallback_individual_verify(self, candidates: List[CandidateMatch]) -> List[VerifyResult]:
        """
        批量调用失败时的单条处理回退
        
        当批量 LLM 调用失败时，尝试逐条调用 verify_and_extract。
        如果单条调用也失败，则根据匹配类型返回默认置信度。
        
        Args:
            candidates: 候选匹配列表
            
        Returns:
            List[VerifyResult]: 验证结果列表，与输入一一对应
        """
        results: List[VerifyResult] = []
        success_count = 0
        fail_count = 0
        threshold = self.config.llm_match_threshold
        
        for idx, candidate in enumerate(candidates):
            try:
                result = self.llm_judge.verify_and_extract(
                    raw_text=candidate.raw_text,
                    customer_name=candidate.customer_name
                )
                results.append(result)
                if result.confidence >= threshold:
                    success_count += 1
            except Exception as e:
                logger.error("Individual verify failed for candidate %d: %s", idx, e)
                fail_count += 1
                # 单条调用失败，根据匹配类型给予默认置信度
                if candidate.match_type == '精确匹配':
                    # 精确匹配在 LLM 失败时给 100 分
                    results.append(VerifyResult(
                        confidence=100,
                        matched_text=candidate.raw_text,
                        reason="LLM调用失败，精确匹配默认通过"
                    ))
                elif candidate.match_type == '脱敏匹配':
                    # 脱敏匹配在 LLM 失败时给 90 分
                    results.append(VerifyResult(
                        confidence=90,
                        matched_text=candidate.raw_text,
                        reason="LLM调用失败，脱敏匹配默认通过"
                    ))
                else:
                    # 模糊匹配在 LLM 失败时给 0 分
                    results.append(VerifyResult(
                        confidence=0,
                        reason="LLM调用失败，模糊匹配需人工确认"
                    ))
        
        if fail_count > 0:
            logger.warning("Individual verify: %d succeeded, %d failed out of %d", 
                          success_count, fail_count, len(candidates))
            self._report_progress(f"单条验证完成: {success_count} 成功, {fail_count} 失败")
        
        return results
    
    def _create_audit_match(self, customer: str, match_result: MatchResult, parse_result: ParseResult, row) -> AuditMatch:
        """创建 AuditMatch 对象"""
        return AuditMatch(
            customer_name=customer,
            matched_text=match_result.matched_text,
            confidence=match_result.match_type.value,
            confidence_score=match_result.confidence,
            source_file=str(parse_result.file_path),
            row_index=row.row_index,
            transaction_time=row.transaction_time or "",
            amount=row.amount or "",
            transaction_type=row.transaction_type or "",
            summary=row.summary or "",
            raw_text=row.raw_text
        )
    
    def _calculate_total_amount(self, matches: List[AuditMatch]) -> float:
        total = 0.0
        for match in matches:
            if match.amount:
                try:
                    amount_str = match.amount.replace(',', '').replace('￥', '')
                    amount_str = amount_str.replace('¥', '').replace('元', '')
                    amount_str = amount_str.replace('+', '').replace('-', '')
                    total += abs(float(amount_str))
                except (ValueError, TypeError):
                    pass
        return total
    
    def _calculate_risk_level(self, matched_customers: int, total_matches: int, total_amount: float) -> RiskLevel:
        if matched_customers >= 5 or total_matches >= 10 or total_amount >= 100000:
            return RiskLevel.HIGH
        elif matched_customers >= 2 or total_matches >= 3 or total_amount >= 10000:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
