# -*- coding: utf-8 -*-
"""Name matching utilities for review workflows."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MatchType(str, Enum):
    """Supported customer-name match types."""

    EXACT = "exact"
    MASKED = "masked"
    FUZZY = "fuzzy"


@dataclass
class MatchResult:
    """Single name match result."""

    customer_name: str
    matched_text: str
    match_type: MatchType
    score: float


class NameMatcher:
    """Match customer names by exact, masked, then fuzzy priority."""

    def __init__(self, fuzzy_threshold: float = 0.6):
        if fuzzy_threshold > 1:
            fuzzy_threshold = fuzzy_threshold / 100
        self.fuzzy_threshold = max(0.0, min(float(fuzzy_threshold), 1.0))
        self._pattern_cache: dict[str, list[re.Pattern[str]]] = {}

    def match(self, customer_name: str, text: str, include_fuzzy: bool = True) -> Optional[MatchResult]:
        """Return the best match for one customer name against text."""
        customer_name = str(customer_name or "").strip()
        text = str(text or "").strip()
        if not customer_name or not text:
            return None

        result = self.match_exact(customer_name, text)
        if result:
            return result

        result = self.match_masked(customer_name, text)
        if result:
            return result

        if include_fuzzy:
            return self.match_fuzzy(customer_name, text)
        return None

    def match_exact(self, customer_name: str, text: str) -> Optional[MatchResult]:
        """Match by direct substring."""
        if customer_name in text:
            return MatchResult(customer_name, customer_name, MatchType.EXACT, 1.0)
        return None

    def match_masked(self, customer_name: str, text: str) -> Optional[MatchResult]:
        """Match masked names such as 张*三 or 张**."""
        for pattern in self._masked_patterns(customer_name):
            found = pattern.search(text)
            if found:
                return MatchResult(customer_name, found.group(0), MatchType.MASKED, 0.9)
        return None

    def match_fuzzy(self, customer_name: str, text: str) -> Optional[MatchResult]:
        """Match similar Chinese-name tokens using sequence similarity."""
        try:
            from Levenshtein import ratio
        except ImportError:
            from difflib import SequenceMatcher

            def ratio(left: str, right: str) -> float:
                return SequenceMatcher(None, left, right).ratio()

        candidates = self._fuzzy_candidates(text, len(customer_name))
        best_text = ""
        best_score = 0.0
        for candidate in candidates:
            score = float(ratio(customer_name, candidate))
            if score > best_score:
                best_score = score
                best_text = candidate

        if best_text and best_score >= self.fuzzy_threshold:
            return MatchResult(customer_name, best_text, MatchType.FUZZY, round(best_score, 4))
        return None

    @staticmethod
    def _fuzzy_candidates(text: str, target_length: int) -> list[str]:
        """Generate compact Chinese substrings near the customer-name length."""
        candidates: list[str] = []
        seen: set[str] = set()
        lengths = range(max(2, target_length - 1), min(8, target_length + 1) + 1)
        for segment in re.findall(r"[\u4e00-\u9fff]{2,12}", text):
            for length in lengths:
                if len(segment) < length:
                    continue
                for start in range(0, len(segment) - length + 1):
                    candidate = segment[start : start + length]
                    if candidate not in seen:
                        seen.add(candidate)
                        candidates.append(candidate)
        return candidates

    def _masked_patterns(self, customer_name: str) -> list[re.Pattern[str]]:
        if customer_name in self._pattern_cache:
            return self._pattern_cache[customer_name]

        escaped = [re.escape(char) for char in customer_name]
        length = len(escaped)
        wildcard = r"[*＊×Xx·\s]{1,3}"
        patterns: list[re.Pattern[str]] = []

        if length < 2:
            self._pattern_cache[customer_name] = patterns
            return patterns

        patterns.append(re.compile(f"{escaped[0]}{wildcard}{escaped[-1]}"))
        patterns.append(re.compile(f"{escaped[0]}{wildcard}"))
        patterns.append(re.compile(f"{wildcard}{escaped[-1]}"))
        if length >= 3:
            patterns.append(re.compile(f"{escaped[0]}{wildcard}{''.join(escaped[-2:])}"))
            patterns.append(re.compile(f"{''.join(escaped[:2])}{wildcard}{escaped[-1]}"))
        if length >= 4:
            patterns.append(re.compile(f"{''.join(escaped[:-1])}{wildcard}"))
            patterns.append(re.compile(f"{wildcard}{''.join(escaped[-3:])}"))

        self._pattern_cache[customer_name] = patterns
        return patterns
