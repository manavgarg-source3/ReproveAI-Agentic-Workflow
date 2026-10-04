"""Paper-level reference validation with per-reference failure isolation."""

import logging
from collections.abc import Iterable

import requests

from app.schemas.research import (
    Reference,
    ReferenceValidation,
    ReferenceValidationStatus,
)
from app.services.scholarly.provider import ScholarlyEvidenceProvider
from app.services.scholarly.scientometric_adapter import ScientometricAdapter

logger = logging.getLogger(__name__)


def _failure_result(
    reference: Reference,
    status: ReferenceValidationStatus,
    note: str,
) -> ReferenceValidation:
    return ReferenceValidation(
        reference_id=reference.id,
        input_doi=reference.doi,
        status=status,
        notes=[note],
        needs_human_review=True,
    )


def validate_references(
    references: Iterable[Reference],
    provider: ScholarlyEvidenceProvider | None = None,
) -> list[ReferenceValidation]:
    """Validate every reference while preserving failures and duplicate inputs."""

    reference_list = list(references)
    if not reference_list:
        return []

    try:
        active_provider = provider or ScientometricAdapter()
    except Exception:
        logger.exception("Scholarly evidence provider could not be initialized")
        return [
            _failure_result(
                reference,
                ReferenceValidationStatus.SOURCE_UNAVAILABLE,
                "The scholarly validation engine is unavailable.",
            )
            for reference in reference_list
        ]

    results: list[ReferenceValidation] = []
    completed: dict[tuple[object, ...], ReferenceValidation] = {}

    for reference in reference_list:
        fingerprint = (
            reference.doi,
            reference.title,
            tuple(reference.authors),
            reference.year,
            reference.citation_text,
        )
        if fingerprint in completed:
            results.append(completed[fingerprint].model_copy(update={"reference_id": reference.id}))
            continue

        try:
            validation = active_provider.validate_reference(reference)
        except (TimeoutError, requests.RequestException) as exc:
            logger.warning(
                "Scholarly source unavailable for reference %s: %s",
                reference.id,
                type(exc).__name__,
            )
            validation = _failure_result(
                reference,
                ReferenceValidationStatus.SOURCE_UNAVAILABLE,
                "A scholarly metadata source was temporarily unavailable.",
            )
        except Exception as exc:
            logger.exception("Reference validation failed for %s", reference.id)
            validation = _failure_result(
                reference,
                ReferenceValidationStatus.ERROR,
                "Bibliographic validation could not be completed for this reference.",
            )

        completed[fingerprint] = validation
        results.append(validation)

    return results
