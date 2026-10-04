"""
Unit tests for URL status interpreter and HTTP classification.
"""
import pytest
from src.validation.url_checker import URLStatusInterpreter


def test_status_classification():
    cases = [
        (200, 0, None, "REACHABLE"),
        (200, 1, None, "REDIRECT_REACHABLE"),
        (401, 0, None, "ACCESS_RESTRICTED"),
        (403, 0, None, "ACCESS_RESTRICTED"),
        (404, 0, None, "BROKEN_NOT_FOUND"),
        (410, 0, None, "GONE"),
        (500, 0, None, "SERVER_ERROR"),
        (None, 0, "TIMEOUT", "TIMEOUT"),
    ]
    for status, redirects, err, expected_cat in cases:
        cat, expl = URLStatusInterpreter.classify(status, redirects, err)
        assert cat == expected_cat, f"Failed for status {status}: got {cat}, expected {expected_cat}"

