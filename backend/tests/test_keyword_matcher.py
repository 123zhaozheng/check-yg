# -*- coding: utf-8 -*-
"""06-23-tab keyword matcher 单测 — 三层（精确/脱敏/模糊 70%）+ 优先级 + 阈值.

覆盖（prd §7）:
* 精确匹配（in 子串，置信度 100）。
* 脱敏匹配（张* / 赵*辰 / 欧**辰 模式，置信度 90）。
* 模糊匹配（Levenshtein ratio，阈值 70%，置信度 = ratio*100）。
* 优先级：精确 > 脱敏 > 模糊，返首个命中。
* 阈值边界：低于 70% 不命中；高于 70% 命中。
* 字段语义：keyword（原 customer_name）+ matched_text + match_type 中文值。
"""

from app.services.keyword.matcher import KeywordMatcher, MatchType


def test_exact_match_returns_100():
    """精确匹配：keyword 是 text 子串 → 置信度 100，match_type 精确匹配。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    r = m.match("张三", "转账给张三 500元")
    assert r is not None
    assert r.match_type == MatchType.EXACT
    assert r.match_type.value == "精确匹配"
    assert r.confidence == 100
    assert r.keyword == "张三"
    assert r.matched_text == "张三"
    assert r.position == (3, 5)


def test_exact_match_not_found_returns_none():
    """keyword 不是子串且无脱敏/模糊命中 → None。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    assert m.match_exact("张三", "李四转账") is None


def test_desensitized_match_2char_pattern():
    """2 字 keyword：张* / *三 模式命中 → 置信度 90。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    r = m.match("张三", "对方：张* 转账")
    assert r is not None
    assert r.match_type == MatchType.DESENSITIZED
    assert r.match_type.value == "脱敏匹配"
    assert r.confidence == 90
    assert r.matched_text == "张*"


def test_desensitized_match_3char_pattern():
    """3 字 keyword：赵*辰 模式命中 → 置信度 90。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    r = m.match("赵北辰", "付款给赵*辰 1000")
    assert r is not None
    assert r.match_type == MatchType.DESENSITIZED
    assert r.confidence == 90
    assert r.matched_text == "赵*辰"


def test_desensitized_match_4char_pattern():
    """4 字 keyword：欧**辰（First + *+ + Last）模式命中 → 置信度 90。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    r = m.match("欧阳北辰", "收款人 欧**辰")
    assert r is not None
    assert r.match_type == MatchType.DESENSITIZED
    assert r.confidence == 90


def test_fuzzy_match_above_threshold():
    """模糊匹配：相似度 >= 70% 命中 → 置信度 = ratio*100。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    # 欧阳北辰 vs 欧阳南辰 → 3/4 = 0.75 >= 0.7 命中。
    r = m.match_fuzzy("欧阳北辰", "收款人 欧阳南辰 转账")
    assert r is not None
    assert r.match_type == MatchType.FUZZY
    assert r.match_type.value == "模糊匹配"
    assert r.confidence >= 70
    assert r.confidence == int(0.75 * 100)  # 75


def test_fuzzy_match_below_threshold_returns_none():
    """模糊匹配：相似度 < 70% → None（阈值边界）。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    # 欧阳明 vs 欧阳鸣 → 2/3 = 0.667 < 0.7。
    r = m.match_fuzzy("欧阳明", "收款人 欧阳鸣 转账")
    assert r is None


def test_fuzzy_threshold_configurable():
    """阈值可配：60% 时欧阳明/欧阳鸣（0.667）命中；50% 时张伟/张玮（0.5）命中。

    模糊层从 text 抽 2-6 字中文片段作候选，候选需与 keyword 长度接近——故用
    隔离的纯名字文本作 text（候选即该名字本身），避免周围汉字把候选拉长。
    """
    m60 = KeywordMatcher(fuzzy_threshold=60)
    r = m60.match_fuzzy("欧阳明", "收款人 欧阳鸣 转账")
    assert r is not None  # 0.667 >= 0.6
    assert r.confidence == 66
    m50 = KeywordMatcher(fuzzy_threshold=50)
    # 隔离文本：候选抽到「张玮」自身，ratio(张伟, 张玮)=0.5 >= 0.5。
    r2 = m50.match_fuzzy("张伟", "张玮")
    assert r2 is not None  # 0.5 >= 0.5
    assert r2.confidence == 50


def test_priority_exact_beats_desensitized():
    """优先级：同一 text 既精确又脱敏可命中 → 返精确（首个命中）。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    # 「张三」精确命中，同时「张*」也存在于 text。
    r = m.match("张三", "张三和张*")
    assert r is not None
    assert r.match_type == MatchType.EXACT
    assert r.matched_text == "张三"


def test_priority_desensitized_beats_fuzzy():
    """优先级：脱敏命中先于模糊。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    # 「张三」不在 text，但「张*」在 → 脱敏命中（模糊层不跑）。
    r = m.match("张三", "对方张* 李四")
    assert r is not None
    assert r.match_type == MatchType.DESENSITIZED


def test_include_fuzzy_false_skips_fuzzy():
    """include_fuzzy=False → 不跑模糊层（仅精确+脱敏）。"""
    m = KeywordMatcher(fuzzy_threshold=70)
    # 无精确/脱敏命中，模糊层本可命中（欧阳北辰/欧阳南辰 0.75）但被禁用 → None。
    r = m.match("欧阳北辰", "收款人 欧阳南辰 转账", include_fuzzy=False)
    assert r is None


def test_empty_text_returns_none():
    """空 text → 无精确/脱敏/模糊命中 → None（不崩）。

    注：空 keyword 在 legacy 行为下因 ``'' in text`` 恒真返精确匹配——这是逐行移植
    保留的 legacy 行为，调用方（service）负责保证 keyword 非空（term 来自 DB 唯一约束）。
    """
    m = KeywordMatcher(fuzzy_threshold=70)
    assert m.match("张三", "") is None
