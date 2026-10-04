"""
Title similarity matching using RapidFuzz and content-word token overlap.
Handles subtitle variations, punctuation changes, stop-word noise, and word-order differences.
"""
from typing import Set
from rapidfuzz import fuzz
from src.parsing.normalizer import normalize_title

STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were",
    "using", "based", "via", "towards", "study", "analysis",
}


class TitleMatcher:
    """
    Computes normalized similarity scores between bibliographic titles.
    """

    @classmethod
    def similarity(cls, title1: str, title2: str) -> float:
        """
        Returns a float between 0.0 and 1.0 representing title similarity.
        """
        t1_norm = normalize_title(title1)
        t2_norm = normalize_title(title2)

        if not t1_norm or not t2_norm:
            return 0.0

        if t1_norm == t2_norm:
            return 1.0

        # Exact substring containment check (common when subtitles are omitted in references)
        if len(t1_norm) > 15 and len(t2_norm) > 15:
            if t1_norm in t2_norm or t2_norm in t1_norm:
                len_ratio = min(len(t1_norm), len(t2_norm)) / max(len(t1_norm), len(t2_norm))
                if len_ratio > 0.60:
                    return max(0.90, round(len_ratio, 4))

        # Tokenize content words
        words1 = set(t1_norm.split())
        words2 = set(t2_norm.split())
        
        c1 = words1 - STOP_WORDS
        c2 = words2 - STOP_WORDS

        # If stripping stop words left nothing, fall back to all words
        if not c1:
            c1 = words1
        if not c2:
            c2 = words2

        # Jaccard overlap on content words
        intersection = c1.intersection(c2)
        union = c1.union(c2)
        jaccard = len(intersection) / len(union) if union else 0.0

        # RapidFuzz token metrics on content-sorted string
        sorted_str1 = " ".join(sorted(c1))
        sorted_str2 = " ".join(sorted(c2))

        token_sort = fuzz.token_sort_ratio(sorted_str1, sorted_str2) / 100.0
        token_set = fuzz.token_set_ratio(t1_norm, t2_norm) / 100.0

        # Weighted blend:
        # If content intersection is completely empty, score should be penalized heavily
        if not intersection:
            score = 0.40 * token_sort
        else:
            score = (0.35 * jaccard) + (0.35 * token_sort) + (0.30 * token_set)

        return min(1.0, max(0.0, round(score, 4)))

