"""Unit tests for structured Gemini analysis without real network calls."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.analysis_errors import (
    AnalysisConfigurationError,
    AnalysisInputTooLargeError,
    AnalysisProviderError,
    AnalysisResponseError,
)
from app.services.llm.gemini import GeminiResearchProvider


VALID_ANALYSIS = {
    "paper": {
        "title": "A Reliable Paper",
        "authors": ["Ada Researcher"],
        "year": 2025,
        "abstract": "We report a controlled evaluation.",
    },
    "claims": [
        {
            "id": "claim-1",
            "claim_text": "The method improves accuracy.",
            "claim_type": "PERFORMANCE",
            "metric": "accuracy",
            "reported_value": 0.91,
            "evidence_locations": ["Abstract"],
        }
    ],
    "experiments": [],
    "methods": ["Controlled evaluation"],
    "references": [],
}


def provider_for_output(output: str) -> tuple[GeminiResearchProvider, Mock]:
    create = Mock(return_value=SimpleNamespace(output_text=output))
    client = SimpleNamespace(interactions=SimpleNamespace(create=create))
    provider = GeminiResearchProvider(
        client=client,
        model="test-model",
        max_characters=1_000,
        timeout_seconds=5,
    )
    return provider, create


def test_valid_structured_gemini_response() -> None:
    provider, create = provider_for_output(json.dumps(VALID_ANALYSIS))

    result = provider.analyze("Paper text")

    assert result.paper.title == "A Reliable Paper"
    assert result.claims[0].reported_value == 0.91
    call = create.call_args.kwargs
    assert call["response_format"][0]["mime_type"] == "application/json"
    assert call["response_format"][0]["schema"]["title"] == "ResearchAnalysis"
    assert set(call["response_format"][0]["schema"]["required"]) == {
        "paper", "claims", "experiments", "methods", "references"
    }


def test_malformed_gemini_response() -> None:
    provider, _ = provider_for_output("not valid JSON")

    with pytest.raises(AnalysisResponseError, match="malformed"):
        provider.analyze("Paper text")


def test_pydantic_validation_failure() -> None:
    invalid = {**VALID_ANALYSIS, "paper": {"title": "Paper", "authors": "not-a-list"}}
    provider, _ = provider_for_output(json.dumps(invalid))

    with pytest.raises(AnalysisResponseError, match="schema validation"):
        provider.analyze("Paper text")


def test_missing_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(AnalysisConfigurationError, match="GEMINI_API_KEY"):
        GeminiResearchProvider()


def test_provider_api_failure() -> None:
    create = Mock(side_effect=RuntimeError("provider unavailable with secret details"))
    client = SimpleNamespace(interactions=SimpleNamespace(create=create))
    provider = GeminiResearchProvider(client=client, model="test-model")

    with pytest.raises(AnalysisProviderError, match="could not complete") as caught:
        provider.analyze("Paper text")

    assert "secret details" not in str(caught.value)


def test_empty_model_response() -> None:
    provider, _ = provider_for_output("  ")

    with pytest.raises(AnalysisResponseError, match="empty response"):
        provider.analyze("Paper text")


def test_oversized_input() -> None:
    provider, create = provider_for_output(json.dumps(VALID_ANALYSIS))
    provider.max_characters = 4

    with pytest.raises(AnalysisInputTooLargeError, match="configured analysis limit"):
        provider.analyze("12345")

    create.assert_not_called()
