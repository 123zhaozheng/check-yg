# -*- coding: utf-8 -*-
"""
AI Table Analyzer - 使用LLM分析表格是否为流水表格并提取表头映射
"""

import json
import logging
from typing import List, Optional, Dict, Any

import requests

from ..parsers.base import (
    HeaderMapping, ColumnMapping, FlowRecord, RawTable
)

logger = logging.getLogger(__name__)


# ============ AI 提示词 ============

SYSTEM_PROMPT_TABLE_ANALYZE = """你是一个银行流水表格分析专家。

## 任务
分析给定的HTML表格片段，判断是否是银行流水表格，如果是则提取表头映射。

## 判断标准
银行流水表格通常包含以下特征：
- 有交易时间/日期列（每行都有不同的交易时间）
- 有金额相关列（每行都有交易金额）
- 有交易对方/对手信息
- 行数据是多条交易记录（至少3条以上）
- 每行代表一笔独立的交易

## 绝对不是流水表格的情况（必须判断为 is_flow_table=false）：
- 账户信息页/个人信息页（包含姓名、地址、邮编、身份证号等）
- 信用卡账单首页（账单日、还款日、本期应还、最低还款额等）
- 账户汇总信息（开户行、账号、余额等静态信息）
- 余额查询结果
- 统计报表/汇总表
- 只有表头没有数据行
- 只有1-2行数据的表格
- 键值对形式的信息展示（如"账单日: 2023-01-12"这种格式）
- 还款明细（只显示还款金额，不是完整交易流水）

## 特别注意
如果表格内容包含以下关键词，很可能不是流水表格：
- 邮编、地址、住址
- 账单日、还款日、到期还款日
- 本期应还、最低还款额
- 信用额度、可用额度
- 开户行、开户日期

## 标准字段（需要映射的目标字段）
1. transaction_time - 交易时间/日期
2. counterparty_name - 交易对手名/对方户名
3. counterparty_account - 交易对手账号
4. amount - 金额/交易金额
5. summary - 摘要/备注
6. transaction_type - 收支类型/交易类型

## 返回JSON格式
{
  "is_flow_table": true或false,
  "confidence": 0-100的整数,
  "reason": "判断理由",
  "header_row_index": 表头所在行索引（0开始）,
  "data_start_row": 数据开始行索引,
  "column_mapping": {
    "transaction_time": 列索引或-1,
    "counterparty_name": 列索引或-1,
    "counterparty_account": 列索引或-1,
    "amount": 列索引或-1,
    "summary": 列索引或-1,
    "transaction_type": 列索引或-1
  }
}"""

SYSTEM_PROMPT_ROW_EXTRACT = """你是一个银行流水数据提取专家。

## 任务
从给定的表格行数据中提取标准化的流水信息，并过滤噪音行。

## 噪音行判断标准（需要丢弃，is_valid设为false）
- 合计行、小计行、总计行
- 空行或只有分隔符的行
- 页眉页脚重复的表头行
- 备注说明行
- 账户信息行（如"账号：xxx"）
- 页码行

## 返回JSON格式
{
  "rows": [
    {
      "is_valid": true,
      "transaction_time": "交易时间",
      "counterparty_name": "对手名",
      "counterparty_account": "对手账号",
      "amount": "金额",
      "summary": "摘要",
      "transaction_type": "收支类型"
    }
  ]
}"""


# JSON Schema for structured output
TABLE_ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_flow_table": {"type": "boolean"},
        "confidence": {"type": "integer"},
        "reason": {"type": "string"},
        "header_row_index": {"type": "integer"},
        "data_start_row": {"type": "integer"},
        "column_mapping": {
            "type": "object",
            "properties": {
                "transaction_time": {"type": "integer"},
                "counterparty_name": {"type": "integer"},
                "counterparty_account": {"type": "integer"},
                "amount": {"type": "integer"},
                "summary": {"type": "integer"},
                "transaction_type": {"type": "integer"}
            },
            "required": ["transaction_time", "counterparty_name", 
                        "counterparty_account", "amount", "summary", "transaction_type"]
        }
    },
    "required": ["is_flow_table", "confidence", "reason", 
                "header_row_index", "data_start_row", "column_mapping"]
}


class TableAnalyzer:
    """
    AI表格分析器
    
    使用LLM分析表格是否为流水表格，并提取表头映射
    """
    
    def __init__(
        self,
        api_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4",
        api_key: str = "",
        timeout: int = 60,
        preview_rows: int = 10
    ):
        self.api_url = api_url.rstrip('/')
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.preview_rows = preview_rows  # 给AI看的行数
    
    def _make_request(
        self, 
        system_prompt: str, 
        user_message: str,
        use_schema: bool = True
    ) -> Optional[Dict[str, Any]]:
        """发送请求到LLM"""
        if not self.api_key:
            logger.warning("No API key configured")
            return None
        
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000,
        }
        
        # 尝试使用 json_schema
        if use_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "table_analysis",
                    "strict": True,
                    "schema": TABLE_ANALYZE_SCHEMA
                }
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            logger.warning("LLM request failed: %s", e)
            # 回退到简单JSON模式
            if use_schema:
                return self._make_request(system_prompt, user_message, False)
            return None
    
    def analyze_table(self, table: RawTable) -> Optional[HeaderMapping]:
        """
        分析表格是否为流水表格并提取表头映射
        
        Args:
            table: 原始表格数据
            
        Returns:
            HeaderMapping if is flow table, None otherwise
        """
        if not table.rows:
            return None
        
        # 构建预览HTML
        preview_html = table.get_preview(self.preview_rows)
        
        # 记录发送给AI的内容（便于调试）
        logger.info("=" * 50)
        logger.info("分析表格 #%d (共%d行)", table.table_index, table.row_count)
        logger.info("发送给AI的预览内容:\n%s", preview_html)
        logger.info("=" * 50)
        
        user_message = f"请分析以下表格：\n\n{preview_html}"
        
        result = self._make_request(SYSTEM_PROMPT_TABLE_ANALYZE, user_message)
        if not result:
            logger.warning("AI请求失败，跳过表格 #%d", table.table_index)
            return None
        
        # 记录AI返回结果
        logger.info("AI判断结果: is_flow_table=%s, confidence=%d%%, reason=%s",
                   result.get('is_flow_table'), 
                   result.get('confidence', 0),
                   result.get('reason', ''))
        
        # 解析结果
        is_flow = result.get('is_flow_table', False)
        if not is_flow:
            logger.info("表格 #%d 不是流水表格，已跳过: %s", 
                       table.table_index, result.get('reason', ''))
            return None
        
        mapping = HeaderMapping(
            is_flow_table=True,
            confidence=result.get('confidence', 0),
            reason=result.get('reason', ''),
            header_row_index=result.get('header_row_index', 0),
            data_start_row=result.get('data_start_row', 1),
            column_mapping=ColumnMapping.from_dict(result.get('column_mapping', {}))
        )
        
        logger.info("流水表格检测成功 #%d (confidence=%d%%): %s", 
                   table.table_index, mapping.confidence, mapping.reason)
        logger.info("列映射: %s", mapping.column_mapping.to_dict())
        return mapping
    
    def extract_rows(
        self,
        table: RawTable,
        mapping: HeaderMapping,
        source_file: str,
        batch_size: int = 20
    ) -> List[FlowRecord]:
        """
        根据表头映射提取流水记录
        
        Args:
            table: 原始表格
            mapping: 表头映射
            source_file: 来源文件名
            batch_size: 每批处理的行数
            
        Returns:
            提取的流水记录列表
        """
        records = []
        data_rows = table.rows[mapping.data_start_row:]
        
        if not data_rows:
            return records
        
        col_map = mapping.column_mapping
        
        # 分批处理
        for i in range(0, len(data_rows), batch_size):
            batch = data_rows[i:i + batch_size]
            batch_records = self._extract_batch(
                batch, col_map, source_file, 
                start_row=mapping.data_start_row + i
            )
            records.extend(batch_records)
        
        return records
    
    def _extract_batch(
        self,
        rows: List[List[str]],
        col_map: ColumnMapping,
        source_file: str,
        start_row: int
    ) -> List[FlowRecord]:
        """
        提取一批行数据（直接按列映射提取，不调用AI）
        
        Args:
            rows: 行数据列表
            col_map: 列映射
            source_file: 来源文件
            start_row: 起始行号
            
        Returns:
            流水记录列表
        """
        records = []
        
        for idx, row in enumerate(rows):
            # 跳过空行
            if not row or all(not cell.strip() for cell in row):
                continue
            
            # 简单噪音过滤（规则兜底）
            row_text = ' '.join(row)
            if self._is_noise_row(row_text):
                continue
            
            # 按列映射提取
            record = FlowRecord(
                source_file=source_file,
                original_row=start_row + idx + 1,
                transaction_time=self._get_cell(row, col_map.transaction_time),
                counterparty_name=self._get_cell(row, col_map.counterparty_name),
                counterparty_account=self._get_cell(row, col_map.counterparty_account),
                amount=self._get_cell(row, col_map.amount),
                summary=self._get_cell(row, col_map.summary),
                transaction_type=self._get_cell(row, col_map.transaction_type),
            )
            records.append(record)
        
        return records
    
    @staticmethod
    def _get_cell(row: List[str], col_index: int) -> str:
        """安全获取单元格值"""
        if col_index < 0 or col_index >= len(row):
            return ""
        return row[col_index].strip()
    
    @staticmethod
    def _is_noise_row(row_text: str) -> bool:
        """判断是否为噪音行"""
        noise_keywords = [
            '合计', '小计', '总计', '本页合计', '累计',
            '以上', '以下', '备注', '说明', '注：',
            '账号：', '户名：', '开户行：',
            '第', '页', '共', 
        ]
        text_lower = row_text.strip()
        
        # 空行
        if not text_lower:
            return True
        
        # 包含噪音关键词
        for keyword in noise_keywords:
            if keyword in text_lower:
                return True
        
        return False
    
    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        return bool(self.api_key)
