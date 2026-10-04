"""
Unit tests for text, title, and author normalization.
"""
import pytest
from src.parsing.normalizer import (
    normalize_title,
    extract_author_parts,
    normalize_author_list,
    normalize_whitespace,
)


def test_normalize_title():
    t1 = "Deep Learning in Healthcare: A Comprehensive Survey!"
    t2 = "deep learning in healthcare a comprehensive survey"
    assert normalize_title(t1) == t2


def test_extract_author_parts():
    cases = [
        ("Smith J.", ("smith", "j")),
        ("Smith, John", ("smith", "j")),
        ("J. Smith", ("smith", "j")),
        ("Prathap G.", ("prathap", "g")),
        ("Gupta B.M.", ("gupta", "bm")),
    ]
    for raw, expected in cases:
        assert extract_author_parts(raw) == expected


def test_normalize_author_list():
    raw = "Prathap G.; Gupta B.M.; Kumar H.A."
    authors = normalize_author_list(raw)
    assert len(authors) == 3
    assert authors[0] == ("prathap", "g")
    assert authors[1] == ("gupta", "bm")
    assert authors[2] == ("kumar", "ha")

