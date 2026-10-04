"""
Unit tests for RapidFuzz title matching, author matching, and compound metadata evaluation.
"""
import pytest
from src.matching.title_matcher import TitleMatcher
from src.matching.author_matcher import AuthorMatcher
from src.matching.metadata_matcher import MetadataMatcher


def test_title_matcher_high_similarity():
    t1 = "Ranking of Indian universities for their research output and quality"
    t2 = "Ranking of Indian Universities for Their Research Output and Quality Using a New Index"
    sim = TitleMatcher.similarity(t1, t2)
    assert sim >= 0.80


def test_title_matcher_low_similarity():
    t1 = "Machine Learning in Healthcare"
    t2 = "Historical Analysis of Medieval Agriculture in Europe"
    sim = TitleMatcher.similarity(t1, t2)
    assert sim < 0.25


def test_author_matcher():
    a1 = "Prathap G.; Gupta B.M."
    a2 = "Gupta, B. M.; Prathap, G."
    sim = AuthorMatcher.similarity(a1, a2)
    assert sim >= 0.70


def test_compound_metadata_matcher():
    cited = {
        "cited_title": "Ranking of Indian universities",
        "cited_authors": "Prathap G.; Gupta B.M.",
        "cited_year": 2009,
        "cited_journal": "Curr. Sci",
        "cited_volume": "97",
        "cited_pages": "751-752",
    }
    resolved = {
        "title": "Ranking of Indian Universities",
        "authors": "Prathap, G.; Gupta, B. M.",
        "year": 2009,
        "journal": "Current Science",
        "volume": "97",
        "pages": "751-752",
    }
    res = MetadataMatcher.evaluate(cited, resolved)
    assert res["composite_score"] >= 0.85
    assert res["year_match"] is True

