"""
Unit tests for LLM-powered Bibliometric Intelligence & Scientometric Audit components.
"""
import pytest
from fastapi.testclient import TestClient

from src.llm.client import LLMClient
from src.llm.citation_extractor import LLMCitationExtractor
from src.llm.citation_intent import CitationIntentClassifier
from src.llm.discrepancy_auditor import LLMDiscrepancyAuditor
from src.llm.scientometric_synthesizer import ScientometricSynthesizer
from src.web.server import app


def test_llm_client_status_and_json_extraction():
    client = LLMClient.get_default()
    status = client.get_status()
    assert "provider" in status
    assert "model" in status
    assert "available" in status

    # Test robust JSON extractor with markdown fences
    raw_response = 'Here is the extracted JSON:\n```json\n{"decision": "MATCH_CONFIRMED", "confidence": 0.95}\n```\nHope this helps!'
    extracted = LLMClient.extract_json(raw_response)
    assert extracted is not None
    assert extracted["decision"] == "MATCH_CONFIRMED"
    assert extracted["confidence"] == 0.95


def test_scientometric_indicators_computation():
    refs = [
        {"cited_year": 2025, "cited_journal": "Nature", "citation_intent": "METHODOLOGY"},
        {"cited_year": 2024, "cited_journal": "Nature", "citation_intent": "METHODOLOGY"},
        {"cited_year": 2022, "cited_journal": "Science", "citation_intent": "BACKGROUND"},
        {"cited_year": 2018, "cited_journal": "IEEE TPAMI", "citation_intent": "COMPARISON"},
        {"cited_year": 2010, "cited_journal": "JMLR", "citation_intent": "CRITIQUE"},
    ]

    # Current year: 2026. 5-year window: >= 2021 (2025, 2024, 2022 -> 3 of 5 = 60%)
    indicators = ScientometricSynthesizer.compute_indicators(refs, current_year=2026)
    assert indicators["total_references"] == 5
    assert indicators["price_index"] == 60.0
    assert indicators["min_year"] == 2010
    assert indicators["max_year"] == 2025
    assert indicators["median_citation_age"] == 4.0  # 2026 - 2022
    assert indicators["venue_diversity_score"] > 0.5
    assert indicators["intent_distribution"]["METHODOLOGY"] == 2
    assert indicators["intent_distribution"]["CRITIQUE"] == 1


def test_citation_intent_classification():
    classifier = CitationIntentClassifier()

    critique_sentence = "However, the method proposed in [10] suffers from severe computational bottlenecks."
    res_critique = classifier.classify(sentence_context=critique_sentence, marker="[10]")
    assert res_critique["intent"] == "CRITIQUE"
    assert res_critique["sentiment"] == "CRITICAL"

    method_sentence = "We adopt the segmentation algorithm from [3] to preprocess the dataset."
    res_method = classifier.classify(sentence_context=method_sentence, marker="[3]")
    assert res_method["intent"] == "METHODOLOGY"

    background_sentence = "Deep learning architectures have revolutionized image classification in recent years [1-4]."
    res_bg = classifier.classify(sentence_context=background_sentence, marker="[1-4]")
    assert res_bg["intent"] in ("BACKGROUND", "METHODOLOGY")


def test_discrepancy_auditor_interface():
    auditor = LLMDiscrepancyAuditor()
    cited = {
        "raw_reference": "Smith, J. (2020). Deep Learning in Healthcare. Medical AI Journal.",
        "cited_title": "Deep Learning in Healthcare",
        "cited_authors": "Smith, J.",
        "cited_year": 2020,
    }
    resolved = {
        "title": "Deep Learning in Healthcare",
        "authors": "Smith, J.",
        "year": 2020,
        "journal": "Medical AI Journal",
    }
    audit_res = auditor.audit(cited, resolved, http_status=200)
    assert "decision" in audit_res
    assert "confidence" in audit_res
    assert "reasoning" in audit_res


def test_fastapi_llm_endpoints():
    client = TestClient(app)

    # 1. Health & LLM status
    res = client.get("/api/llm/status")
    assert res.status_code == 200
    assert "provider" in res.json()

    # 2. Citation intent endpoint
    res_intent = client.post(
        "/api/llm/citation-intent",
        json={
            "sentence_context": "Following the architecture in [7], we implement a residual network.",
            "marker": "[7]",
        },
    )
    assert res_intent.status_code == 200
    assert "intent" in res_intent.json()

    # 3. Synthesize audit endpoint
    res_synth = client.post(
        "/api/llm/synthesize-audit",
        json={
            "doc_title": "Test Manuscript",
            "references": [
                {"cited_year": 2023, "cited_journal": "IEEE Trans", "citation_intent": "METHODOLOGY"},
                {"cited_year": 2022, "cited_journal": "ACM Comput", "citation_intent": "BACKGROUND"},
            ],
            "document_diagnostics": {"consistency_score": 95},
        },
    )
    assert res_synth.status_code == 200
    data = res_synth.json()
    assert "indicators" in data
    assert "price_index" in data["indicators"]
    assert "executive_summary" in data

