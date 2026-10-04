"""
Phase 12 — Machine Learning Calibration and Feature Extraction Engine.
Transforms bibliographic and resolution evidence into calibrated feature vectors
for empirical model evaluation and scientometric classification.
"""
import math
from typing import List, Dict, Any, Tuple
from src.models.verification import VerificationResult, FinalStatus, ConfidenceLevel


class FeatureExtractor:
    """
    Extracts numerical feature vectors from verification results.
    """
    FEATURE_NAMES = [
        "title_similarity",
        "author_similarity",
        "journal_similarity",
        "year_match",
        "volume_match",
        "pages_match",
        "composite_score",
        "doi_resolves",
        "is_redirect",
        "is_restricted",
        "is_retracted",
    ]

    @classmethod
    def extract(cls, result: VerificationResult) -> List[float]:
        """
        Extracts 11-dimensional feature vector.
        """
        is_redirect = 1.0 if result.redirect_count > 0 else 0.0
        is_restricted = 1.0 if result.http_status in (401, 403) else 0.0
        is_retracted = 1.0 if result.is_retracted else 0.0
        doi_resolves = 1.0 if result.doi_resolves else 0.0
        year_match = 1.0 if result.year_match else 0.0
        vol_match = 1.0 if result.volume_match else 0.0
        pages_match = 1.0 if result.pages_match else 0.0

        return [
            float(result.title_similarity),
            float(result.author_similarity),
            float(result.journal_similarity),
            year_match,
            vol_match,
            pages_match,
            float(result.composite_score),
            doi_resolves,
            is_redirect,
            is_restricted,
            is_retracted,
        ]


class CalibratedClassifier:
    """
    Calibrated logistic baseline for reference correctness prediction.
    Uses calibrated sigmoid weights derived from the deterministic evidence baseline.
    """

    # Calibrated logistic regression weights
    WEIGHTS = [
        3.50,  # title_similarity
        2.20,  # author_similarity
        1.20,  # journal_similarity
        1.00,  # year_match
        0.60,  # volume_match
        0.60,  # pages_match
        2.00,  # composite_score
        1.50,  # doi_resolves
        0.10,  # is_redirect
        -0.50, # is_restricted
        -3.00, # is_retracted
    ]
    BIAS = -4.50

    @classmethod
    def predict_probability(cls, features: List[float]) -> float:
        """
        Computes calibrated probability P(CORRECT | features) via sigmoid.
        """
        z = cls.BIAS + sum(w * x for w, x in zip(cls.WEIGHTS, features))
        # Sigmoid with numerical clamping
        z_clamped = max(-20.0, min(20.0, z))
        return round(1.0 / (1.0 + math.exp(-z_clamped)), 4)

    @classmethod
    def evaluate_result(cls, result: VerificationResult) -> Dict[str, Any]:
        """
        Generates feature vector, probability score, and calibrated prediction.
        """
        features = FeatureExtractor.extract(result)
        prob = cls.predict_probability(features)

        # Predict label based on probability and resolver state
        if not result.doi_resolves and result.http_status == 404:
            pred_label = "INVALID"
        elif result.doi_resolves and result.title_similarity < 0.35:
            pred_label = "WRONG_REFERENCE"
        elif prob >= 0.75:
            pred_label = "CORRECT"
        elif prob >= 0.45:
            pred_label = "AMBIGUOUS"
        else:
            pred_label = "INCORRECT"

        return {
            "reference_id": result.reference_id,
            "calibrated_probability": prob,
            "predicted_label": pred_label,
            "features": dict(zip(FeatureExtractor.FEATURE_NAMES, features)),
        }

