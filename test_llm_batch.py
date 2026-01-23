# -*- coding: utf-8 -*-
"""
测试 LLMJudge.verify_and_extract_batch 功能（置信度版本）
"""

import sys
sys.path.insert(0, '.')

from src.config import get_config
from src.core.auditor import CandidateMatch
from src.llm.judge import LLMJudge

def main():
    # 加载配置
    config = get_config()
    print(f"LLM URL: {config.llm_url}")
    print(f"LLM Model: {config.llm_model}")
    print(f"API Key: {'已配置' if config.llm_api_key else '未配置'}")
    print(f"Batch Size: {config.llm_batch_size}")
    print(f"Match Threshold: {config.llm_match_threshold}%")
    print("-" * 50)
    
    # 初始化 LLMJudge
    llm_judge = LLMJudge(
        api_url=config.llm_url,
        model=config.llm_model,
        api_key=config.llm_api_key,
        batch_size=config.llm_batch_size,
        custom_system_prompt=config.llm_system_prompt
    )
    
    threshold = config.llm_match_threshold
    
    # 伪造候选匹配列表 - 包含各种场景
    candidates = [
        # 场景1: 精确匹配
        CandidateMatch(
            raw_text="2024-01-15 10:30:00 转账 张三 5000.00元 工资发放",
            customer_name="张三",
            source_file="银行流水.xlsx",
            row_index=1,
            match_type="精确匹配"
        ),
        # 场景2: 脱敏匹配 - 应该高置信度
        CandidateMatch(
            raw_text="2024-01-16 14:20:00 收入 Z******0010/*德元 3000.00元 报销款",
            customer_name="刘德元",
            source_file="建行活期明细.xlsx",
            row_index=2,
            match_type="脱敏匹配"
        ),
        # 场景3: 脱敏匹配 - 另一种格式
        CandidateMatch(
            raw_text="2024-01-17 09:15:00 支出 *德元 2000.00元 借款",
            customer_name="刘德元",
            source_file="银行流水.xlsx",
            row_index=3,
            match_type="脱敏匹配"
        ),
        # 场景4: 店铺名误匹配 - 应该低置信度
        CandidateMatch(
            raw_text="2024-01-18 16:45:00 支出 众晶**店 6.71元 消费",
            customer_name="王众晶",
            source_file="支付宝流水.xlsx",
            row_index=4,
            match_type="模糊匹配"
        ),
        # 场景5: 店铺名误匹配 - 另一个例子
        CandidateMatch(
            raw_text="2024-01-19 11:00:00 支出 好佳福优选超市-高明店 160.57元 购物",
            customer_name="高明建",
            source_file="支付宝流水.xlsx",
            row_index=5,
            match_type="模糊匹配"
        ),
    ]
    
    print(f"准备验证 {len(candidates)} 条候选匹配:")
    for i, c in enumerate(candidates, 1):
        print(f"  [{i}] 客户: {c.customer_name}, 类型: {c.match_type}")
        print(f"      原文: {c.raw_text}")
    print("-" * 50)
    
    # 调用批量验证
    print("正在调用 LLM 批量验证...")
    try:
        results = llm_judge.verify_and_extract_batch(candidates)
        
        print(f"\n验证完成，返回 {len(results)} 个结果:")
        print("-" * 50)
        
        passed_count = 0
        for i, (candidate, result) in enumerate(zip(candidates, results), 1):
            status = "✓ 通过" if result.confidence >= threshold else "✗ 拒绝"
            if result.confidence >= threshold:
                passed_count += 1
            
            print(f"\n[{i}] 客户: {candidate.customer_name} - {status}")
            print(f"    置信度: {result.confidence}% (阈值: {threshold}%)")
            print(f"    matched_text: {result.matched_text}")
            print(f"    reason: {result.reason}")
            if result.confidence >= threshold:
                print(f"    transaction_time: {result.transaction_time}")
                print(f"    amount: {result.amount}")
                print(f"    transaction_type: {result.transaction_type}")
        
        # 统计
        print("\n" + "=" * 50)
        print(f"统计: {passed_count}/{len(results)} 条通过验证 (阈值: {threshold}%)")
        
    except Exception as e:
        print(f"验证失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
