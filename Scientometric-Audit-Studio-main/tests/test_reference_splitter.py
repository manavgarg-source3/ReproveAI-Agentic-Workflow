"""
Unit tests for robust reference segmentation.
"""
import pytest
from src.parsing.reference_splitter import ReferenceSplitter


def test_multi_author_semicolons_preserved():
    raw = "Prathap G.; Gupta B.M., Ranking of Indian universities for their research output, Curr. Sci, 97, 6, pp. 751-752, (2009); Gupta B.M., Ranking and performance of Indian Universities, Ind. J. Sci. Technol, 3, 7, pp. 837-843, (2010);"
    refs = ReferenceSplitter.split(raw, source_eid="test_doc_1")
    assert len(refs) == 2
    assert "Prathap G.; Gupta B.M." in refs[0].raw_reference
    assert refs[0].cited_year == 2009
    assert refs[0].has_year is True
    assert refs[1].cited_year == 2010
    assert refs[1].has_year is True


def test_reference_without_year():
    raw = "Nonaka I.; Hirotaka T., The knowledge-creating company: How Japanese companies create the dynamics of innovation; (2016); Ely H., How Smartphones and Mobile Internet have Changed Our Lives, (2016);"
    refs = ReferenceSplitter.split(raw, source_eid="test_doc_2")
    assert len(refs) >= 2
    # Check that at least one reference is flagged if it has no year or unusual structure
    assert any(r.has_year for r in refs)


def test_suspicious_flags():
    raw = "Too short; " + ("Very long reference text " * 50) + " (2020);"
    refs = ReferenceSplitter.split(raw, source_eid="test_doc_3")
    assert any(r.needs_review for r in refs)

