"""
Author matching and comparison engine.
Matches author surnames and initials tolerant of different formatting conventions.
"""
from typing import List, Tuple
from rapidfuzz import fuzz
from src.parsing.normalizer import normalize_author_list, extract_author_parts


class AuthorMatcher:
    """
    Compares author lists for bibliographic correspondence.
    """

    @classmethod
    def similarity(cls, authors_str1: str, authors_str2: str) -> float:
        """
        Returns a float between 0.0 and 1.0 representing author correspondence.
        """
        list1 = normalize_author_list(authors_str1)
        list2 = normalize_author_list(authors_str2)

        if not list1 or not list2:
            # Fallback to loose fuzzy matching if structured extraction yielded nothing
            if authors_str1 and authors_str2:
                return round(fuzz.token_set_ratio(authors_str1.lower(), authors_str2.lower()) / 100.0, 4)
            return 0.0

        surnames1 = [p[0] for p in list1 if p[0]]
        surnames2 = [p[0] for p in list2 if p[0]]
        
        # Surnames sets
        s1 = set(p[0] for p in list1 if p[0])
        s2 = set(p[0] for p in list2 if p[0])

        if not s1 or not s2:
            return 0.0

        # Jaccard overlap on surnames
        intersection = s1.intersection(s2)
        union = s1.union(s2)
        jaccard = len(intersection) / len(union) if union else 0.0

        # Check first author match (first author is standardly dominant)
        first_author_match = 0.0
        if list1[0][0] == list2[0][0]:
            first_author_match = 0.90
            # If initial also matches
            if list1[0][1] and list2[0][1] and list1[0][1][0] == list2[0][1][0]:
                first_author_match = 1.0
        elif list1[0][0] in s2 or list2[0][0] in s1:
            first_author_match = 0.60

        # Blend: 50% first author + 50% overall surname overlap
        score = (0.50 * first_author_match) + (0.50 * jaccard)
        return min(1.0, max(0.0, round(score, 4)))

