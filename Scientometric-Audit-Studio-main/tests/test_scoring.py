"""
Unit tests for scoring, decision engine, and VALID_DOI_WRONG_REFERENCE detection.
"""
import pytest
from src.matching.scoring import DecisionEngine
from src.models.verification import FinalStatus, ConfidenceLevel


def test_valid_correct():
    match_scores = {
        "composite_score": 0.95,
        "title_similarity": 0.98,
        "year_match": True,
    }
    resolver_result = {
        "doi_exists": True,
        "doi_resolves": True,
        "http_status": 200,
        "redirect_count": 0,
    }
    status, conf, rationale, review = DecisionEngine.classify_with_doi(match_scores, resolver_result)
    assert status == FinalStatus.VALID_CORRECT
    assert conf == ConfidenceLevel.HIGH
    assert review is False


def test_valid_doi_wrong_reference():
    """
    CRITICAL SPECIFICATION REQUIREMENT:
    DOI resolves to 200 OK, but metadata matches a completely different paper.
    Must be classified as VALID_DOI_WRONG_REFERENCE.
    """
    match_scores = {
        "composite_score": 0.15,
        "title_similarity": 0.10,
        "year_match": False,
    }
    resolver_result = {
        "doi_exists": True,
        "doi_resolves": True,
        "http_status": 200,
        "redirect_count": 1,
    }
    status, conf, rationale, review = DecisionEngine.classify_with_doi(match_scores, resolver_result)
    assert status == FinalStatus.VALID_DOI_WRONG_REFERENCE
    assert review is True


def test_invalid_doi():
    match_scores = {"composite_score": 0.0, "title_similarity": 0.0}
    resolver_result = {
        "doi_exists": False,
        "doi_resolves": False,
        "http_status": 404,
    }
    status, conf, rationale, review = DecisionEngine.classify_with_doi(match_scores, resolver_result)
    assert status == FinalStatus.INVALID_DOI
    assert review is True


def test_access_restricted():
    match_scores = {
        "composite_score": 0.90,
        "title_similarity": 0.92,
    }
    resolver_result = {
        "doi_exists": True,
        "doi_resolves": True,
        "http_status": 403,
    }
    status, conf, rationale, review = DecisionEngine.classify_with_doi(match_scores, resolver_result)
    assert status == FinalStatus.ACCESS_RESTRICTED


def test_doi_recovered():
    match_scores = {
        "composite_score": 0.92,
        "title_similarity": 0.95,
    }
    cand = {"doi": "10.1000/182"}
    resolver_result = {"doi_exists": True, "doi_resolves": True, "http_status": 200}
    status, conf, rationale, review = DecisionEngine.classify_recovered_doi(match_scores, cand, resolver_result)
    assert status == FinalStatus.DOI_RECOVERED
    assert conf == ConfidenceLevel.HIGH

