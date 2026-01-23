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

SYSTEM_PROMPT_TABLE_ANALYZE = """你是一个银行流水表格分析专家，熟悉中国各大银行、支付宝、微信支付、信用卡的流水格式。

## 任务
分析给定的HTML表格片段，判断是否是银行/支付流水表格，如果是则提取表头映射。

## 判断标准
流水表格通常包含以下特征：
- 有交易时间/日期列（每行都有不同的交易时间）
- 有金额相关列（每行都有交易金额）
- 有交易对方/对手信息（部分流水可能没有）
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

## 各平台流水表头常见名称对照表

### 银行储蓄卡流水
| 标准字段 | 工商银行 | 建设银行 | 农业银行 | 中国银行 | 招商银行 | 交通银行 | 民生银行 | 浦发银行 |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| transaction_time | 交易日期、记账日期 | 交易时间、记账日期 | 交易日期 | 交易日期、记账日期 | 交易日期、交易时间 | 交易日期 | 交易日期 | 交易日期 |
| counterparty_name | 对方户名、对方名称 | 对方户名 | 对方户名、收/付方名称 | 对方户名 | 对方户名、交易对手 | 对方户名 | 对方户名 | 对方户名 |
| counterparty_account | 对方账号、对方卡号 | 对方账号 | 对方账号 | 对方账号 | 对方账号 | 对方账号 | 对方账号 | 对方账号 |
| amount | 交易金额、发生额 | 交易金额、发生额 | 交易金额 | 交易金额、借方发生额、贷方发生额 | 交易金额 | 交易金额 | 交易金额 | 交易金额 |
| summary | 摘要、交易摘要、备注 | 摘要、交易备注 | 摘要 | 摘要 | 摘要、交易摘要 | 摘要 | 摘要 | 摘要 |
| transaction_type | 收/支、借/贷、交易类型 | 收支标志、借贷标志 | 收支类型 | 借贷标志 | 收支类型 | 收支标志 | 收支类型 | 收支类型 |

### 信用卡账单流水
| 标准字段 | 常见表头名称 |
|---------|------------|
| transaction_time | 交易日期、交易时间、记账日期、入账日期、消费日期 |
| counterparty_name | 交易描述、商户名称、交易说明、消费说明、交易对象 |
| counterparty_account | （信用卡通常无此字段，设为-1） |
| amount | 交易金额、人民币金额、记账金额、消费金额、入账金额 |
| summary | 交易描述、备注、交易说明（可能与counterparty_name同列） |
| transaction_type | 收/支、存入/支出（信用卡多为支出，还款为存入） |

### 支付宝流水
| 标准字段 | 常见表头名称 |
|---------|------------|
| transaction_time | 交易时间、交易创建时间、创建时间 |
| counterparty_name | 交易对方、对方、商家、收款方、付款方 |
| counterparty_account | 对方账号（可能为空或脱敏显示如 ***.com） |
| amount | 金额、交易金额、金额(元) |
| summary | 商品说明、商品名称、交易备注、备注 |
| transaction_type | 收/支、收入/支出、资金状态 |

### 微信支付流水
| 标准字段 | 常见表头名称 |
|---------|------------|
| transaction_time | 交易时间 |
| counterparty_name | 交易对方、商户名称 |
| counterparty_account | （微信通常无此字段，设为-1） |
| amount | 金额(元)、支出(元)、收入(元) |
| summary | 商品、交易类型、备注 |
| transaction_type | 收/支（或通过金额正负判断） |

## 示例1：工商银行储蓄卡流水
表头行：交易日期 | 摘要 | 对方户名 | 对方账号 | 收入 | 支出 | 余额
映射结果：
- transaction_time: 0 (交易日期)
- summary: 1 (摘要)
- counterparty_name: 2 (对方户名)
- counterparty_account: 3 (对方账号)
- amount: 4 或 5 (收入/支出，优先选择有数据的列，或选择靠前的金额列)
- transaction_type: -1 (无明确列，可通过收入/支出列判断)

## 示例2：招商银行信用卡账单
表头行：交易日期 | 记账日期 | 交易描述 | 交易金额
映射结果：
- transaction_time: 0 (交易日期)
- counterparty_name: 2 (交易描述)
- counterparty_account: -1 (无)
- amount: 3 (交易金额)
- summary: 2 (交易描述，与counterparty_name同列)
- transaction_type: -1 (无明确列)

## 示例3：支付宝流水
表头行：交易时间 | 交易对方 | 对方账号 | 商品说明 | 收/支 | 金额
映射结果：
- transaction_time: 0 (交易时间)
- counterparty_name: 1 (交易对方)
- counterparty_account: 2 (对方账号)
- summary: 3 (商品说明)
- transaction_type: 4 (收/支)
- amount: 5 (金额)

## 示例4：微信支付流水
表头行：交易时间 | 交易类型 | 交易对方 | 商品 | 收/支 | 金额(元)
映射结果：
- transaction_time: 0 (交易时间)
- counterparty_name: 2 (交易对方)
- counterparty_account: -1 (无)
- summary: 3 (商品)
- transaction_type: 4 (收/支)
- amount: 5 (金额)

## 标准字段说明
1. transaction_time - 交易发生的时间，格式可能是"2024-01-15"或"2024-01-15 14:30:25"
2. counterparty_name - 交易对手方名称，如"张三"、"淘宝商家"、"美团外卖"
3. counterparty_account - 交易对手方账号，如银行卡号、支付宝账号（部分流水无此字段）
4. amount - 交易金额，可能带正负号或在不同列（收入/支出）
5. summary - 交易摘要或备注，描述交易用途，如"工资"、"转账"、"消费"
6. transaction_type - 收支类型，如"收入"、"支出"、"借"、"贷"

## 映射规则
1. 找不到对应列时设为 -1
2. 如果收入和支出是两列，amount 映射到其中一列（优先支出列），另一列信息可通过后处理合并
3. 如果交易描述同时包含对方名称和摘要信息，可以同时映射到 counterparty_name 和 summary
4. 表头可能在第0行，也可能在第1、2行（前面有标题行）
5. 数据行通常紧跟表头行之后
6. 可以参考文档名称推断流水来源（如文件名包含"工商"、"建行"、"支付宝"、"微信"等关键词）

## 返回JSON格式
{
  "is_flow_table": true或false,
  "confidence": 0-100的整数,
  "reason": "判断理由，说明识别为哪种类型的流水",
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
        "is_flow_table": {
            "type": "boolean",
            "description": "是否为流水表格。true表示是银行/支付宝/微信等交易流水表格，false表示不是"
        },
        "confidence": {
            "type": "integer",
            "description": "判断置信度，0-100的整数。80以上表示高度确信，60-80表示较确信，60以下表示不太确定"
        },
        "reason": {
            "type": "string",
            "description": "判断理由，说明为什么判断为流水表格或非流水表格，以及识别出的流水类型（如：工商银行储蓄卡流水、招商银行信用卡账单、支付宝流水、微信支付流水等）"
        },
        "header_row_index": {
            "type": "integer",
            "description": "表头所在行的索引（从0开始）。如果表格第一行是标题，表头可能在第1行或第2行"
        },
        "data_start_row": {
            "type": "integer",
            "description": "数据开始行的索引（从0开始）。通常是header_row_index + 1，但有时表头和数据之间有空行"
        },
        "column_mapping": {
            "type": "object",
            "description": "列映射关系，将表格列索引映射到标准字段。找不到对应列时设为-1",
            "properties": {
                "transaction_time": {
                    "type": "integer",
                    "description": "交易时间列索引。对应表头：交易日期、交易时间、记账日期、入账日期、创建时间等。-1表示未找到"
                },
                "counterparty_name": {
                    "type": "integer",
                    "description": "交易对方名称列索引。对应表头：对方户名、交易对方、商户名称、交易描述、收款方、付款方等。-1表示未找到"
                },
                "counterparty_account": {
                    "type": "integer",
                    "description": "交易对方账号列索引。对应表头：对方账号、对方卡号。信用卡和微信流水通常无此字段，设为-1"
                },
                "amount": {
                    "type": "integer",
                    "description": "交易金额列索引。对应表头：交易金额、金额、发生额、收入、支出、金额(元)等。如有收入/支出两列，优先选择支出列或靠前的金额列"
                },
                "summary": {
                    "type": "integer",
                    "description": "摘要/备注列索引。对应表头：摘要、交易摘要、备注、商品说明、交易备注等。可能与counterparty_name同列。-1表示未找到"
                },
                "transaction_type": {
                    "type": "integer",
                    "description": "收支类型列索引。对应表头：收/支、借/贷、收支标志、资金状态等。-1表示未找到（可通过金额正负或收入/支出列判断）"
                }
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
    
    def analyze_table(
        self, 
        table: RawTable, 
        document_name: str = ""
    ) -> Optional[HeaderMapping]:
        """
        分析表格是否为流水表格并提取表头映射
        
        Args:
            table: 原始表格数据
            document_name: 文档名称（用于辅助AI判断流水来源）
            
        Returns:
            HeaderMapping if is flow table, None otherwise
        """
        if not table.rows:
            return None
        
        # 构建预览HTML
        preview_html = table.get_preview(self.preview_rows)
        
        # 记录发送给AI的内容（便于调试）
        logger.info("=" * 50)
        logger.info("分析表格 #%d (共%d行) 来自文档: %s", 
                   table.table_index, table.row_count, document_name)
        logger.info("发送给AI的预览内容:\n%s", preview_html)
        logger.info("=" * 50)
        
        # 构建用户消息，包含文档名称
        if document_name:
            user_message = f"文档名称：{document_name}\n\n请分析以下表格：\n\n{preview_html}"
        else:
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
