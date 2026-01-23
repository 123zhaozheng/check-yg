# -*- coding: utf-8 -*-
"""
Name matching engine
Supports exact, desensitized, and fuzzy matching
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Pattern, Tuple

logger = logging.getLogger(__name__)


class MatchType(Enum):
    """Match type enumeration"""
    EXACT = "精确匹配"
    DESENSITIZED = "脱敏匹配"
    FUZZY = "模糊匹配"


@dataclass
class MatchResult:
    """Match result data class"""
    customer_name: str      # Original customer name
    matched_text: str       # Text that was matched
    match_type: MatchType   # Type of match
    confidence: int         # Confidence percentage (0-100)
    position: Tuple[int, int] = (0, 0)  # Start and end position in text


class NameMatcher:
    """
    Name matching engine supporting multiple match strategies
    
    Match priority:
    1. Exact match (100%)
    2. Desensitized match (90%)
    3. Fuzzy match (configurable threshold)
    """
    
    def __init__(self, fuzzy_threshold: int = 60):
        """
        Initialize matcher
        
        Args:
            fuzzy_threshold: Minimum similarity for fuzzy match (0-100)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self._pattern_cache: dict = {}
    
    def generate_desensitized_patterns(self, name: str) -> List[Pattern]:
        """
        Generate regex patterns for desensitized name matching
        
        Patterns for different name lengths:
        - 2 chars: 张* / *三
        - 3 chars: 赵*辰 / *北辰 / 赵北*
        - 4 chars: 欧阳*辰 / 欧**辰 / *阳北辰 / 欧阳北*
        
        Args:
            name: Full customer name
            
        Returns:
            List of compiled regex patterns
        """
        if name in self._pattern_cache:
            return self._pattern_cache[name]
        
        patterns = []
        name_len = len(name)
        
        if name_len < 2:
            self._pattern_cache[name] = patterns
            return patterns
        
        # Escape special regex characters in name
        escaped_chars = [re.escape(c) for c in name]
        
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
        
        self._pattern_cache[name] = patterns
        return patterns
    
    def match_exact(self, name: str, text: str) -> Optional[MatchResult]:
        """
        Perform exact match
        
        Args:
            name: Customer name to match
            text: Text to search in
            
        Returns:
            MatchResult if found, None otherwise
        """
        if name in text:
            pos = text.find(name)
            return MatchResult(
                customer_name=name,
                matched_text=name,
                match_type=MatchType.EXACT,
                confidence=100,
                position=(pos, pos + len(name))
            )
        return None
    
    def match_desensitized(self, name: str, text: str) -> Optional[MatchResult]:
        """
        Perform desensitized match using generated patterns
        
        Args:
            name: Customer name to match
            text: Text to search in
            
        Returns:
            MatchResult if found, None otherwise
        """
        patterns = self.generate_desensitized_patterns(name)
        
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return MatchResult(
                    customer_name=name,
                    matched_text=match.group(),
                    match_type=MatchType.DESENSITIZED,
                    confidence=90,
                    position=(match.start(), match.end())
                )
        
        return None
    
    def match_fuzzy(self, name: str, text: str) -> Optional[MatchResult]:
        """
        Perform fuzzy match using Levenshtein distance
        
        Args:
            name: Customer name to match
            text: Text to search in
            
        Returns:
            MatchResult if similarity >= threshold, None otherwise
        """
        try:
            from Levenshtein import ratio
        except ImportError:
            logger.warning("python-Levenshtein not installed, fuzzy match disabled")
            return None
        
        # Extract potential name candidates from text
        # Look for sequences of Chinese characters
        candidates = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
        
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            score = ratio(name, candidate) * 100
            if score >= self.fuzzy_threshold and score > best_score:
                best_score = score
                best_match = candidate
        
        if best_match:
            pos = text.find(best_match)
            return MatchResult(
                customer_name=name,
                matched_text=best_match,
                match_type=MatchType.FUZZY,
                confidence=int(best_score),
                position=(pos, pos + len(best_match))
            )
        
        return None
    
    def match(self, name: str, text: str, include_fuzzy: bool = True) -> Optional[MatchResult]:
        """
        Perform matching with priority: exact > desensitized > fuzzy
        
        Args:
            name: Customer name to match
            text: Text to search in
            include_fuzzy: Whether to include fuzzy matching
            
        Returns:
            Best MatchResult if found, None otherwise
        """
        # Try exact match first
        result = self.match_exact(name, text)
        if result:
            return result
        
        # Try desensitized match
        result = self.match_desensitized(name, text)
        if result:
            return result
        
        # Try fuzzy match if enabled
        if include_fuzzy:
            result = self.match_fuzzy(name, text)
            if result:
                return result
        
        return None
    
    def find_all_matches(self, name: str, text: str, include_fuzzy: bool = True) -> List[MatchResult]:
        """
        Find all matches for a name in text
        
        Args:
            name: Customer name to match
            text: Text to search in
            include_fuzzy: Whether to include fuzzy matching
            
        Returns:
            List of all MatchResults found
        """
        results = []
        
        # Find all exact matches
        for match in re.finditer(re.escape(name), text):
            results.append(MatchResult(
                customer_name=name,
                matched_text=name,
                match_type=MatchType.EXACT,
                confidence=100,
                position=(match.start(), match.end())
            ))
        
        # Find all desensitized matches
        patterns = self.generate_desensitized_patterns(name)
        for pattern in patterns:
            for match in pattern.finditer(text):
                # Avoid duplicates
                if not any(r.position == (match.start(), match.end()) for r in results):
                    results.append(MatchResult(
                        customer_name=name,
                        matched_text=match.group(),
                        match_type=MatchType.DESENSITIZED,
                        confidence=90,
                        position=(match.start(), match.end())
                    ))
        
        # Fuzzy match returns at most one result
        if include_fuzzy and not results:
            fuzzy_result = self.match_fuzzy(name, text)
            if fuzzy_result:
                results.append(fuzzy_result)
        
        return results
