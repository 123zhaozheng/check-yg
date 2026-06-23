# -*- coding: utf-8 -*-
"""关键词三层匹配引擎（06-23-tab 关键词审查）.

移植 legacy ``src/core/matcher.py`` 的 ``NameMatcher`` 三层逻辑到 web 后端：
* 精确匹配（``in`` 子串，置信度 100）。
* 脱敏匹配（正则 ``张*`` / ``赵*辰`` / ``欧**辰`` 模式，置信度 90）。
* 模糊匹配（Levenshtein ratio，阈值默认 70%，置信度 = ratio*100）。

优先级：精确 > 脱敏 > 模糊，返首个命中。

与 legacy 的差异（按 prd §B 匹配引擎）：
* ``customer_name`` 参数语义换成 ``keyword``（被匹配文本仍是流水字段值）。
* ``MatchResult`` 字段名改 ``keyword`` / ``matched_text`` / ``match_type`` /
  ``confidence`` / ``position``。
* ``match_type`` 用中文枚举值（精确匹配/脱敏匹配/模糊匹配），对齐命中表存储。
* 模糊层阈值默认 70（prd §B），fallback 用标准库 ``difflib.SequenceMatcher``
  并 log 降级（Levenshtein 装不上时）。

不删减 legacy 匹配算法/优先级/阈值——逐行移植，仅改字段语义。
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Callable, List, Optional, Pattern, Tuple

logger = logging.getLogger(__name__)


# 模糊层降级标记：Levenshtein 装不上时 fallback 到 difflib，只 log 一次避免刷屏。
_FUZZY_DOWNGRADE_WARNED = False


def _get_fuzzy_ratio() -> Callable[[str, str], float]:
    """返回模糊相似度函数（0-1）。

    优先用 ``Levenshtein.ratio``（C 扩展，快）；装不上时 fallback 到标准库
    ``difflib.SequenceMatcher`` 的 ``ratio()``（纯 Python，语义一致：2*匹配/总长），
    并 log 一次 WARNING 说明降级（prd §B：装不上则降级 + log）。

    Returns:
        ``ratio(a, b) -> float``，范围 0.0-1.0。
    """
    global _FUZZY_DOWNGRADE_WARNED
    try:
        from Levenshtein import ratio as _lev_ratio  # type: ignore[import]

        return _lev_ratio
    except ImportError:
        if not _FUZZY_DOWNGRADE_WARNED:
            logger.warning(
                "python-Levenshtein not installed, fuzzy match 降级到 difflib.SequenceMatcher"
            )
            _FUZZY_DOWNGRADE_WARNED = True

        def _difflib_ratio(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio()

        return _difflib_ratio


class MatchType(Enum):
    """Match type enumeration (中文值，对齐命中表存储)."""

    EXACT = "精确匹配"
    DESENSITIZED = "脱敏匹配"
    FUZZY = "模糊匹配"


@dataclass
class MatchResult:
    """Match result data class.

    ``keyword`` = 被匹配的关键词（原 customer_name 语义）。
    ``matched_text`` = 实际命中片段文本。
    """

    keyword: str
    matched_text: str
    match_type: MatchType
    confidence: int  # 0-100
    position: Tuple[int, int] = (0, 0)


# 模糊层阈值默认 70%（prd §B）。
DEFAULT_FUZZY_THRESHOLD = 70


class KeywordMatcher:
    """
    Keyword matching engine supporting multiple match strategies.

    Match priority:
    1. Exact match (100%)
    2. Desensitized match (90%)
    3. Fuzzy match (configurable threshold, default 70%)
    """

    def __init__(self, fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD):
        """
        Initialize matcher.

        Args:
            fuzzy_threshold: Minimum similarity for fuzzy match (0-100)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self._pattern_cache: dict[str, List[Pattern]] = {}

    def generate_desensitized_patterns(self, keyword: str) -> List[Pattern]:
        """
        Generate regex patterns for desensitized keyword matching.

        Patterns for different keyword lengths:
        - 2 chars: 张* / *三
        - 3 chars: 赵*辰 / *北辰 / 赵北*
        - 4 chars: 欧阳*辰 / 欧**辰 / *阳北辰 / 欧阳北*
        """
        if keyword in self._pattern_cache:
            return self._pattern_cache[keyword]

        patterns: List[Pattern] = []
        name_len = len(keyword)

        if name_len < 2:
            self._pattern_cache[keyword] = patterns
            return patterns

        # Escape special regex characters in keyword.
        escaped_chars = [re.escape(c) for c in keyword]

        if name_len == 2:
            # 张* / *三
            patterns.append(re.compile(f"{escaped_chars[0]}[*＊]"))
            patterns.append(re.compile(f"[*＊]{escaped_chars[1]}"))

        elif name_len == 3:
            # 赵*辰 / *北辰 / 赵北*
            patterns.append(re.compile(f"{escaped_chars[0]}[*＊]{escaped_chars[2]}"))
            patterns.append(re.compile(f"[*＊]{escaped_chars[1]}{escaped_chars[2]}"))
            patterns.append(re.compile(f"{escaped_chars[0]}{escaped_chars[1]}[*＊]"))
            # Also match: 赵**
            patterns.append(re.compile(f"{escaped_chars[0]}[*＊]{{2}}"))

        elif name_len >= 4:
            # 欧阳*辰 / 欧**辰 / *阳北辰 / 欧阳北*
            # First + * + Last
            patterns.append(re.compile(f"{escaped_chars[0]}[*＊]+{escaped_chars[-1]}"))
            # First two + * + Last
            patterns.append(re.compile(f"{''.join(escaped_chars[:2])}[*＊]+{escaped_chars[-1]}"))
            # * + Last three
            patterns.append(re.compile(f"[*＊]+{''.join(escaped_chars[-3:])}"))
            # First + * + Last two
            patterns.append(re.compile(f"{escaped_chars[0]}[*＊]+{''.join(escaped_chars[-2:])}"))
            # All but last + *
            patterns.append(re.compile(f"{''.join(escaped_chars[:-1])}[*＊]+"))

        self._pattern_cache[keyword] = patterns
        return patterns

    def match_exact(self, keyword: str, text: str) -> Optional[MatchResult]:
        """
        Perform exact match.

        Args:
            keyword: Keyword to match
            text: Text to search in

        Returns:
            MatchResult if found, None otherwise
        """
        if keyword in text:
            pos = text.find(keyword)
            return MatchResult(
                keyword=keyword,
                matched_text=keyword,
                match_type=MatchType.EXACT,
                confidence=100,
                position=(pos, pos + len(keyword)),
            )
        return None

    def match_desensitized(self, keyword: str, text: str) -> Optional[MatchResult]:
        """
        Perform desensitized match using generated patterns.

        Args:
            keyword: Keyword to match
            text: Text to search in

        Returns:
            MatchResult if found, None otherwise
        """
        patterns = self.generate_desensitized_patterns(keyword)

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return MatchResult(
                    keyword=keyword,
                    matched_text=match.group(),
                    match_type=MatchType.DESENSITIZED,
                    confidence=90,
                    position=(match.start(), match.end()),
                )

        return None

    def match_fuzzy(self, keyword: str, text: str) -> Optional[MatchResult]:
        """
        Perform fuzzy match using Levenshtein distance.

        Fallback to ``difflib.SequenceMatcher`` when python-Levenshtein not
        installed（降级 log 只打一次，避免逐词刷屏）。

        Args:
            keyword: Keyword to match
            text: Text to search in

        Returns:
            MatchResult if similarity >= threshold, None otherwise
        """
        ratio_fn = _get_fuzzy_ratio()

        # Extract potential name candidates from text — sequences of Chinese chars.
        candidates = re.findall(r"[一-鿿]{2,6}", text)

        best_match: Optional[str] = None
        best_score = 0.0

        for candidate in candidates:
            score = float(ratio_fn(keyword, candidate)) * 100
            if score >= self.fuzzy_threshold and score > best_score:
                best_score = score
                best_match = candidate

        if best_match:
            pos = text.find(best_match)
            return MatchResult(
                keyword=keyword,
                matched_text=best_match,
                match_type=MatchType.FUZZY,
                confidence=int(best_score),
                position=(pos, pos + len(best_match)),
            )

        return None

    def match(self, keyword: str, text: str, include_fuzzy: bool = True) -> Optional[MatchResult]:
        """
        Perform matching with priority: exact > desensitized > fuzzy.

        Args:
            keyword: Keyword to match
            text: Text to search in
            include_fuzzy: Whether to include fuzzy matching

        Returns:
            Best MatchResult if found, None otherwise
        """
        # Try exact match first.
        result = self.match_exact(keyword, text)
        if result:
            return result

        # Try desensitized match.
        result = self.match_desensitized(keyword, text)
        if result:
            return result

        # Try fuzzy match if enabled.
        if include_fuzzy:
            result = self.match_fuzzy(keyword, text)
            if result:
                return result

        return None
