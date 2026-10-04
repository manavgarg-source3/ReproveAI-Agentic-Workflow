"""Adapter tests with mocked Scientometric engine responses."""

from types import SimpleNamespace

import pytest

from app.schemas.research import (
    Reference,
    ReferenceValidation,
    ReferenceValidationStatus,
)
from app.services.scholarly.scientometric_adapter import (
    ScientometricAdapter,
    _parse_numbered_reference_fields,
)
from app.services.scholarly.validation import validate_references


class FakeParsedReference:
    def __init__(self, **values):
        self.__dict__.update(values)


def engine_result(status: str, **overrides):
    values = {
        "final_status": SimpleNamespace(value=status),
        "confidence": SimpleNamespace(value="HIGH"),
        "normalized_doi": "10.1000/example",
        "doi_resolves": True,
        "resolved_title": "Matching title",
        "resolved_authors": "Researcher, Ada; Scientist, Grace",
        "resolved_year": 2020,
        "resolved_journal": "Journal of Tests",
        "composite_score": 0.97,
        "needs_human_review": False,
        "decision_rationale": "Deterministic engine decision.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeValidator:
    def __init__(self, result):
        self.result = result
        self.received = []

    def validate_reference(self, reference):
        self.received.append(reference)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_reference(**overrides) -> Reference:
    values = {
        "id": "REF-001",
        "citation_text": "Ada Researcher. Matching title. 2020. doi:10.1000/example",
        "title": "Matching title",
        "authors": ["Ada Researcher"],
        "year": 2020,
        "doi": "https://doi.org/10.1000/example",
    }
    values.update(overrides)
    return Reference(**values)


@pytest.mark.parametrize(
    ("engine_status", "score", "expected"),
    [
        ("VALID_CORRECT", 0.97, ReferenceValidationStatus.VALID_CORRECT),
        ("METADATA_MISMATCH", 0.68, ReferenceValidationStatus.METADATA_MISMATCH),
        (
            "VALID_DOI_WRONG_REFERENCE",
            0.12,
            ReferenceValidationStatus.VALID_DOI_WRONG_REFERENCE,
        ),
        ("INVALID_DOI", 0.0, ReferenceValidationStatus.INVALID_DOI),
        ("DOI_MISSING", 0.0, ReferenceValidationStatus.DOI_MISSING),
    ],
)
def test_adapter_preserves_engine_statuses(engine_status, score, expected) -> None:
    validator = FakeValidator(engine_result(engine_status, composite_score=score))
    adapter = ScientometricAdapter(
        validator=validator,
        parsed_reference_type=FakeParsedReference,
        normalize_doi_fn=lambda value: value.removeprefix("https://doi.org/"),
    )

    result = adapter.validate_reference(make_reference())

    assert result.status == expected
    assert result.metadata_match_score == score
    assert result.source is None


def test_valid_doi_matching_metadata_maps_complete_evidence() -> None:
    validator = FakeValidator(engine_result("VALID_CORRECT", metadata_source="crossref"))
    adapter = ScientometricAdapter(
        validator=validator,
        parsed_reference_type=FakeParsedReference,
    )

    result = adapter.validate_reference(make_reference())

    assert result.normalized_doi == "10.1000/example"
    assert result.doi_resolves is True
    assert result.matched_title == "Matching title"
    assert result.matched_authors == ["Researcher, Ada", "Scientist, Grace"]
    assert result.matched_year == 2020
    assert result.matched_venue == "Journal of Tests"
    assert ReferenceValidation.model_validate(result.model_dump()) == result


def test_invalid_doi_is_passed_to_existing_engine() -> None:
    validator = FakeValidator(
        engine_result(
            "INVALID_DOI",
            normalized_doi="",
            doi_resolves=False,
            composite_score=0.0,
        )
    )
    adapter = ScientometricAdapter(
        validator=validator,
        parsed_reference_type=FakeParsedReference,
    )

    result = adapter.validate_reference(make_reference(doi="not-a-doi"))

    assert validator.received[0].extracted_doi == "not-a-doi"
    assert result.normalized_doi is None
    assert result.status == ReferenceValidationStatus.INVALID_DOI


def test_missing_doi_and_incomplete_metadata_are_safe() -> None:
    validator = FakeValidator(
        engine_result(
            "DOI_MISSING",
            normalized_doi="",
            doi_resolves=False,
            resolved_title="",
            resolved_authors="",
            resolved_year=None,
            resolved_journal="",
            composite_score=0.0,
        )
    )
    adapter = ScientometricAdapter(
        validator=validator,
        parsed_reference_type=FakeParsedReference,
    )

    result = adapter.validate_reference(
        make_reference(title=None, authors=[], year=None, doi=None)
    )

    received = validator.received[0]
    assert received.cited_title == ""
    assert received.cited_authors == ""
    assert received.cited_year is None
    assert received.extracted_doi == ""
    assert result.status == ReferenceValidationStatus.DOI_MISSING


class MixedProvider:
    def validate_reference(self, reference: Reference) -> ReferenceValidation:
        if reference.id == "REF-002":
            raise TimeoutError("provider timeout containing internal details")
        return ReferenceValidation(
            reference_id=reference.id,
            input_doi=reference.doi,
            normalized_doi="10.1000/example",
            doi_resolves=True,
            status=ReferenceValidationStatus.VALID_CORRECT,
        )


def test_multiple_references_isolate_provider_failure() -> None:
    references = [
        make_reference(),
        make_reference(
            id="REF-002",
            citation_text="A distinct reference that times out.",
            title="Distinct title",
        ),
        make_reference(id="REF-003"),
    ]

    results = validate_references(references, provider=MixedProvider())

    assert [result.status for result in results] == [
        ReferenceValidationStatus.VALID_CORRECT,
        ReferenceValidationStatus.SOURCE_UNAVAILABLE,
        ReferenceValidationStatus.VALID_CORRECT,
    ]
    assert "internal details" not in results[1].notes[0]


def test_duplicate_identical_references_reuse_result() -> None:
    provider = FakeValidator(engine_result("VALID_CORRECT"))
    adapter = ScientometricAdapter(
        validator=provider,
        parsed_reference_type=FakeParsedReference,
    )
    references = [make_reference(), make_reference(id="REF-DUPLICATE")]

    results = validate_references(references, provider=adapter)

    assert len(provider.received) == 1
    assert [item.reference_id for item in results] == ["REF-001", "REF-DUPLICATE"]


@pytest.mark.parametrize(
    ("citation", "expected_title", "expected_authors"),
    [
        (
            "[1] Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. "
            "Layer normalization. arXiv preprint arXiv:1607.06450, 2016.",
            "Layer normalization",
            ["Jimmy Lei Ba", "Jamie Ryan Kiros", "Geoffrey E Hinton"],
        ),
        (
            "[8] Chris Dyer, Adhiguna Kuncoro, Miguel Ballesteros, and Noah A. "
            "Smith. Recurrent neural network grammars. In Proc. of NAACL, 2016.",
            "Recurrent neural network grammars",
            ["Chris Dyer", "Adhiguna Kuncoro", "Miguel Ballesteros", "Noah A. Smith"],
        ),
        (
            "[10] Alex Graves. Generating sequences with recurrent neural networks. "
            "arXiv preprint arXiv:1308.0850, 2013.",
            "Generating sequences with recurrent neural networks",
            ["Alex Graves"],
        ),
        (
            "[VSP+17] Ashish Vaswani, Noam Shazeer, and Niki Parmar. "
            "Attention is all you need. Advances in Neural Information Processing "
            "Systems, 2017.",
            "Attention is all you need",
            ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        ),
    ],
)
def test_numbered_reference_fields_are_recovered_without_final_author_leakage(
    citation, expected_title, expected_authors
) -> None:
    title, authors = _parse_numbered_reference_fields(citation)

    assert title == expected_title
    assert authors == expected_authors
