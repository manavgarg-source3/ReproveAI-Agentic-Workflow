"""
Unit tests for RapidFuzz title matching, author matching, and compound metadata evaluation.
"""
import pytest
from src.matching.title_matcher import TitleMatcher
from src.matching.author_matcher import AuthorMatcher
from src.matching.metadata_matcher import MetadataMatcher
from src.validation.recovery import DOIRecoveryEngine


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


def test_sparse_arxiv_metadata_is_normalized_over_available_fields():
    cited = {
        "cited_title": "Intrinsic Dimensionality Explains the Effectiveness of Language Model Fine-Tuning",
        "cited_authors": "Armen Aghajanyan; Luke Zettlemoyer; Sonal Gupta",
        "cited_year": 2020,
        "cited_journal": "",
        "cited_volume": "",
        "cited_pages": "",
    }
    resolved = {
        "title": "Intrinsic Dimensionality Explains the Effectiveness of Language Model Fine-Tuning",
        "authors": "Aghajanyan, Armen; Zettlemoyer, Luke; Gupta, Sonal",
        "year": 2021,
        "journal": "",
        "volume": "",
        "pages": "",
    }

    result = MetadataMatcher.evaluate(cited, resolved)

    assert result["title_similarity"] == 1.0
    assert result["year_match"] is True
    assert result["composite_score"] >= 0.85


def test_page_ranges_match_across_unicode_and_ascii_dashes():
    cited = {
        "cited_title": "Transformers: State-of-the-Art Natural Language Processing",
        "cited_authors": "Thomas Wolf; Lysandre Debut",
        "cited_year": 2020,
        "cited_pages": "38–45",
    }
    resolved = {
        "title": cited["cited_title"],
        "authors": cited["cited_authors"],
        "year": 2020,
        "pages": "38-45",
    }

    result = MetadataMatcher.evaluate(cited, resolved)

    assert result["pages_match"] is True
    assert result["vol_pages_score"] == 0.6


def test_recovery_compares_all_registries_before_selecting_candidate():
    class Scopus:
        def is_available(self):
            return True

        def search_by_title_and_author(self, title, author, count=2):
            return [{
                "provider": "scopus",
                "doi": "10.0000/near-match",
                "title": f"{title} extended edition",
                "authors": author,
                "year": 2020,
            }]

    class Crossref:
        def is_available(self):
            return True

        def search_bibliographic(self, query, rows=3):
            return [{
                "provider": "crossref",
                "doi": "10.0000/exact-match",
                "title": "An Exact Bibliographic Title",
                "authors": "Ada Lovelace",
                "year": 2020,
            }]

    class OpenAlex:
        def is_available(self):
            return False

    cited = {
        "cited_title": "An Exact Bibliographic Title",
        "cited_authors": "Ada Lovelace",
        "cited_year": 2020,
    }
    candidate, _scores = DOIRecoveryEngine(
        crossref=Crossref(), openalex=OpenAlex(), scopus=Scopus()
    ).recover(cited)

    assert candidate["doi"] == "10.0000/exact-match"

