"""
Unit tests for ML feature extraction and calibration baseline.
"""
import pytest
from src.matching.classifier import FeatureExtractor, CalibratedClassifier
from src.models.verification import VerificationResult, FinalStatus, ConfidenceLevel


def test_feature_extractor():
    res = VerificationResult(
        reference_id="test_doc_001",
        source_eid="test_doc",
        reference_no=1,
        raw_reference="Smith J., (2020)",
        title_similarity=0.95,
        author_similarity=0.88,
        journal_similarity=0.75,
        year_match=True,
        volume_match=True,
        pages_match=True,
        composite_score=0.91,
        doi_resolves=True,
        redirect_count=1,
        is_retracted=False,
    )
    features = FeatureExtractor.extract(res)
    assert len(features) == 11
    assert features[0] == 0.95  # title_similarity
    assert features[7] == 1.0   # doi_resolves
    assert features[8] == 1.0   # is_redirect


def test_calibrated_classifier_prediction():
    res_correct = VerificationResult(
        reference_id="test_doc_002",
        source_eid="test_doc",
        reference_no=2,
        raw_reference="Smith J., Machine Learning (2020)",
        title_similarity=0.98,
        author_similarity=0.90,
        composite_score=0.92,
        doi_resolves=True,
    )
    eval_res = CalibratedClassifier.evaluate_result(res_correct)
    assert eval_res["calibrated_probability"] >= 0.80
    assert eval_res["predicted_label"] == "CORRECT"

