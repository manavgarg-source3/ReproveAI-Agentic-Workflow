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


def test_line_wrapped_author_year_bibliography_splits_each_entry():
    blob = (
        "Armen Aghajanyan, Luke Zettlemoyer, and Sonal Gupta. Intrinsic Dimensionality Explains the\n"
        "Effectiveness of Language Model Fine-Tuning. arXiv:2012.13255 [cs], December 2020. URL\n"
        "http://arxiv.org/abs/2012.13255.\n"
        "Zeyuan Allen-Zhu and Yuanzhi Li. What Can ResNet Learn Efficiently, Going Beyond Kernels? In\n"
        "NeurIPS, 2019. Full version available at http://arxiv.org/abs/1905.10337.\n"
        "Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E. Hinton. Layer normalization, 2016.\n"
    )

    references = ReferenceSplitter.split_manuscript_references(blob)

    assert len(references) == 3
    assert references[0].startswith("Armen Aghajanyan")
    assert references[1].startswith("Zeyuan Allen-Zhu")
    assert references[2].startswith("Jimmy Lei Ba")


def test_inline_author_after_terminal_year_starts_a_new_reference():
    blob = (
        "Geoffrey Hinton, Oriol Vinyals, and Jeff Dean. Distilling the knowledge in a neural "
        "network, 2015. Jonathan J. Hull. A database for handwritten text recognition research. "
        "IEEE Transactions on Pattern Analysis and Machine Intelligence, 16(5):550-554, 1994.\n"
        "Ricardo Henao. A study presented at CVPR 2009.\n"
        "IEEE Conference on, pp. 1-8. Ieee, 2009. "
        "Justin Domke. Generic methods for optimization-based modeling. In AISTATS, 2012."
    )

    references = ReferenceSplitter.split_manuscript_references(blob)

    assert len(references) == 4
    assert references[1].startswith("Jonathan J. Hull")
    assert "IEEE Conference" in references[2]
    assert references[3].startswith("Justin Domke")

