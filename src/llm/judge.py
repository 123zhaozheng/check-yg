# -*- coding: utf-8 -*-
"""
LLM Judge module for AI-assisted match confirmation and transaction extraction
Supports OpenAI-compatible APIs with concurrent requests
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from ..core.auditor import CandidateMatch

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    """
    大模型验证结果
    
    统一验证接口的返回结果，包含匹配置信度和交易详情提取。
    confidence 为 0-100 的整数，表示 LLM 判断该交易属于指定客户的置信度。
    """
    confidence: int = 0
    matched_text: str = ""
    transaction_time: str = ""
    amount: str = ""
    transaction_type: str = ""
    summary: str = ""
    reason: str = ""


class LLMJudge:
    """
    LLM-based judge for confirming fuzzy matches and extracting transaction info.
    Uses concurrent requests for batch processing.
    """
    
    # 默认系统提示词
    DEFAULT_SYSTEM_PROMPT_VERIFY = """你是一个银行流水审计助手。给定一条银行流水记录和一个客户姓名，你需要：

1. 判断这条流水的交易对方是否是该客户，并给出置信度（0-100）
2. 提取完整的交易信息

## 判断步骤（必须按顺序执行）

### 第一步：提取真正的人名部分
流水中的交易对方可能包含前缀，需要先提取出真正的人名：
- "支付宝-张*" → 人名是 "张*"
- "微信-*三" → 人名是 "*三"  
- "4******9202/*成停" → 人名是 "*成停"
- "Z******0010/*德元" → 人名是 "*德元"
- "财付通-李*明" → 人名是 "李*明"
- "高小名便利店" → 人名是 "高小名"

### 第二步：比较人名字数
- 每个*代表一个被隐藏的字
- 提取出的人名字数必须与客户姓名字数相同
- 例如：客户"高成"(2字) vs 提取人名"*成停"(3字) → 字数不同，判0分
- 例如：客户"张三"(2字) vs 提取人名"*三"(2字) → 字数相同，继续判断

### 第三步：比较可见字符的位置
- 脱敏人名中可见的字必须与客户姓名对应位置的字相同
- 例如：客户"刘德元" vs "*德元" → 第2字"德"、第3字"元"都对应 → 匹配
- 例如：客户"高成" vs "*成停" → 字数不同 → 不匹配
- 例如：客户"沈旭风" vs "李旭风" → 第1字"沈"≠"李" → 姓不同，判0分

## 置信度评分标准

【100分】完全一致
【90分】字数相同 + 可见字符位置完全对应（如"刘德元"vs"*德元"）
【80分】字数相同 + 可见字符对应 + 有账号前缀，或有轻微OCR错误
【60分】有一定相似性但不完全确定
【0-30分】字数不同、姓氏不同等

## 必须判0分的情况
- 客户"高成"(2字) vs "*成停"(3字) → 0分（字数不同）
- 客户"沈旭风" vs "李旭风" → 0分（姓不同）

## 返回JSON格式（必须严格遵守）
你必须返回一个JSON对象，包含以下字段：
{
  "confidence": 整数0-100，匹配置信度，0表示明确不匹配，100表示完全确定匹配,
  "matched_text": "原文中的交易对方名称，保持原样",
  "transaction_time": "交易时间",
  "amount": "交易金额",
  "transaction_type": "交易类型（收入/支出/转账等）",
  "summary": "摘要/备注",
  "reason": "判断理由（简短说明）"
}"""

    # JSON Schema
    VERIFY_SCHEMA = {
        "type": "object",
        "properties": {
            "confidence": {"type": "integer"},
            "matched_text": {"type": "string"},
            "transaction_time": {"type": "string"},
            "amount": {"type": "string"},
            "transaction_type": {"type": "string"},
            "summary": {"type": "string"},
            "reason": {"type": "string"}
        },
        "required": ["confidence", "matched_text", "transaction_time", "amount", "transaction_type", "summary", "reason"],
        "additionalProperties": False
    }

    def __init__(
        self,
        api_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4",
        api_key: str = "",
        batch_size: int = 10,
        timeout: int = 60,
        custom_system_prompt: str = ""
    ):
        self.api_url = api_url.rstrip('/')
        self.model = model
        self.api_key = api_key
        self.batch_size = batch_size  # 并发数
        self.timeout = timeout
        
        # 使用自定义提示词或默认提示词
        self.system_prompt = custom_system_prompt.strip() if custom_system_prompt.strip() else self.DEFAULT_SYSTEM_PROMPT_VERIFY

    def _make_single_request(
        self, 
        raw_text: str,
        customer_name: str
    ) -> VerifyResult:
        """发送单个请求到 LLM"""
        if not self.api_key or not raw_text.strip():
            return VerifyResult(confidence=0)
        
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        user_message = f"客户姓名：{customer_name}\n\n银行流水记录：\n{raw_text}"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "verify_result",
                    "strict": True,
                    "schema": self.VERIFY_SCHEMA
                }
            }
        }
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            content = response.json()['choices'][0]['message']['content'].strip()
            result = json.loads(content)
            
            # 解析置信度
            confidence = result.get('confidence', 0)
            if isinstance(confidence, str):
                try:
                    confidence = int(confidence)
                except ValueError:
                    confidence = 0
            confidence = max(0, min(100, int(confidence)))
            
            return VerifyResult(
                confidence=confidence,
                matched_text=str(result.get('matched_text', '') or ''),
                transaction_time=str(result.get('transaction_time', '') or ''),
                amount=str(result.get('amount', '') or ''),
                transaction_type=str(result.get('transaction_type', '') or ''),
                summary=str(result.get('summary', '') or ''),
                reason=str(result.get('reason', '') or '')
            )
            
        except Exception as e:
            logger.warning("LLM request failed: %s", e)
            # 尝试简单 JSON 模式
            return self._make_single_request_simple(raw_text, customer_name)
    
    def _make_single_request_simple(
        self, 
        raw_text: str,
        customer_name: str
    ) -> VerifyResult:
        """使用简单 JSON 模式发送请求（兼容不支持 json_schema 的 API）"""
        if not self.api_key or not raw_text.strip():
            return VerifyResult(confidence=0)
        
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        user_message = f"客户姓名：{customer_name}\n\n银行流水记录：\n{raw_text}"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            content = response.json()['choices'][0]['message']['content'].strip()
            result = json.loads(content)
            
            confidence = result.get('confidence', 0)
            if isinstance(confidence, str):
                try:
                    confidence = int(confidence)
                except ValueError:
                    confidence = 0
            confidence = max(0, min(100, int(confidence)))
            
            return VerifyResult(
                confidence=confidence,
                matched_text=str(result.get('matched_text', '') or ''),
                transaction_time=str(result.get('transaction_time', '') or ''),
                amount=str(result.get('amount', '') or ''),
                transaction_type=str(result.get('transaction_type', '') or ''),
                summary=str(result.get('summary', '') or ''),
                reason=str(result.get('reason', '') or '')
            )
            
        except Exception as e:
            logger.error("LLM simple request also failed: %s", e)
            return VerifyResult(confidence=0)
    
    def verify_and_extract(
        self, 
        raw_text: str, 
        customer_name: str
    ) -> VerifyResult:
        """
        验证单条记录并提取交易信息
        """
        return self._make_single_request(raw_text, customer_name)
    
    def verify_and_extract_batch(
        self, 
        candidates: List['CandidateMatch']
    ) -> List[VerifyResult]:
        """
        并发验证多条记录
        
        使用线程池并发发送请求，batch_size 控制并发数。
        每个请求只处理一条记录。
        
        Args:
            candidates: 候选匹配列表
            
        Returns:
            验证结果列表，与输入顺序一一对应
        """
        if not candidates:
            return []
        
        if not self.api_key:
            logger.warning("No API key configured for LLM")
            return [VerifyResult(confidence=0) for _ in candidates]
        
        # 使用字典保存结果，key 是索引
        results_dict: Dict[int, VerifyResult] = {}
        
        def process_single(idx: int, candidate: 'CandidateMatch') -> tuple:
            """处理单个候选"""
            result = self._make_single_request(candidate.raw_text, candidate.customer_name)
            return idx, result
        
        # 使用线程池并发请求
        with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
            futures = {
                executor.submit(process_single, i, c): i 
                for i, c in enumerate(candidates)
            }
            
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results_dict[idx] = result
                except Exception as e:
                    idx = futures[future]
                    logger.error("Failed to process candidate %d: %s", idx, e)
                    results_dict[idx] = VerifyResult(confidence=0)
        
        # 按原始顺序返回结果
        return [results_dict.get(i, VerifyResult(confidence=0)) for i in range(len(candidates))]
    
    def is_available(self) -> bool:
        """Check if LLM service is available"""
        return bool(self.api_key)
