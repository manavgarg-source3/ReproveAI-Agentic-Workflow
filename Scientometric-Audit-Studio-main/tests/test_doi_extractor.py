"""
Unit tests for DOI extraction and canonical normalization.
"""
import pytest
from src.parsing.doi_extractor import extract_doi, normalize_doi, extract_url


def test_doi_formats():
    cases = [
        ("doi:10.1038/nature12373", "10.1038/nature12373"),
        ("DOI: 10.1038/nature12373.", "10.1038/nature12373"),
        ("https://doi.org/10.1038/nature12373;", "10.1038/nature12373"),
        ("http://dx.doi.org/10.1016/j.joi.2020.101088", "10.1016/j.joi.2020.101088"),
        ("Available at: https://doi.org/10.1108/JD-12-2019-0242)", "10.1108/JD-12-2019-0242"),
    ]
    for raw, expected in cases:
        extracted = extract_doi(raw)
        assert extracted == expected, f"Failed for raw: {raw}"


def test_normalize_doi_balanced_parens():
    # DOIs with balanced parentheses in suffix should be preserved
    doi = "10.1002/(sici)1097-4571(1998)49:1<12::aid-asi3>3.0.co;2-z"
    normalized = normalize_doi(doi)
    assert normalized == doi.lower()


def test_extract_url():
    text = "See research at https://www.nature.com/articles/45678.pdf for details."
    url = extract_url(text)
    assert url == "https://www.nature.com/articles/45678.pdf"

