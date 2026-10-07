"""Paper-level reference validation with per-reference failure isolation."""

import logging
import os
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
    
    # Keep a configurable safety bound for exceptionally large surveys while
    # validating ordinary bibliographies in full.
    validation_limit = max(1, int(os.getenv("SCHOLARLY_VALIDATION_LIMIT", "100")))
    original_count = len(reference_list)
    if original_count > validation_limit:
        logger.warning(
            "Capping validation to %d references (out of %d) to prevent timeout.",
            validation_limit,
            original_count,
        )
        
        # We still need to return validation stubs for the skipped ones so the frontend doesn't break
        skipped = reference_list[validation_limit:]
        reference_list = reference_list[:validation_limit]
    else:
        skipped = []
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

    results_by_fingerprint: dict[tuple[object, ...], ReferenceValidation] = {}

    import concurrent.futures

    def _fingerprint(reference: Reference) -> tuple[object, ...]:
        return (
            reference.doi,
            reference.title,
            tuple(reference.authors),
            reference.year,
            reference.citation_text,
        )

    def _process_ref(reference):
        fingerprint = (
            reference.doi,
            reference.title,
            tuple(reference.authors),
            reference.year,
            reference.citation_text,
        )
        try:
            validation = active_provider.validate_reference(reference)
        except Exception as exc:
            import requests
            if isinstance(exc, (TimeoutError, requests.RequestException)):
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
            else:
                logger.exception("Reference validation failed for %s", reference.id)
                validation = _failure_result(
                    reference,
                    ReferenceValidationStatus.ERROR,
                    "Bibliographic validation could not be completed for this reference.",
                )
        return validation, fingerprint

    unique_references: dict[tuple[object, ...], Reference] = {}
    for reference in reference_list:
        unique_references.setdefault(_fingerprint(reference), reference)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(unique_references))) as executor:
        future_to_ref = {
            executor.submit(_process_ref, reference): fingerprint
            for fingerprint, reference in unique_references.items()
        }
        for future in concurrent.futures.as_completed(future_to_ref):
            try:
                validation, fingerprint = future.result()
                results_by_fingerprint[fingerprint] = validation
            except Exception:
                pass

    results = [
        results_by_fingerprint[_fingerprint(reference)].model_copy(
            update={"reference_id": reference.id}
        )
        for reference in reference_list
        if _fingerprint(reference) in results_by_fingerprint
    ]
    results.extend(
        _failure_result(
            reference,
            ReferenceValidationStatus.SOURCE_UNAVAILABLE,
            "Reference validation was skipped because the request safety limit was reached.",
        )
        for reference in skipped
    )
    return results
