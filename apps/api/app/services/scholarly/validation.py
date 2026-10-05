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
    
    # PERFORMANCE SAFEGUARD: Survey papers can have 300+ references.
    # We cap validation to 25 to avoid 15-minute HTTP timeouts.
    original_count = len(reference_list)
    if original_count > 25:
        logger.warning(f"Capping validation to 25 references (out of {original_count}) to prevent timeout.")
        
        # We still need to return validation stubs for the skipped ones so the frontend doesn't break
        skipped = reference_list[25:]
        reference_list = reference_list[:25]
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

    results: list[ReferenceValidation] = []
    completed: dict[tuple[object, ...], ReferenceValidation] = {}
    
    import concurrent.futures

    def _process_ref(reference):
        fingerprint = (
            reference.doi,
            reference.title,
            tuple(reference.authors),
            reference.year,
            reference.citation_text,
        )
        if fingerprint in completed:
            return completed[fingerprint].model_copy(update={"reference_id": reference.id}), fingerprint, True

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
        return validation, fingerprint, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        future_to_ref = {executor.submit(_process_ref, ref): ref for ref in reference_list}
        for future in concurrent.futures.as_completed(future_to_ref):
            try:
                validation, fingerprint, is_cached = future.result()
                if not is_cached:
                    completed[fingerprint] = validation
                results.append(validation)
            except Exception:
                pass

    return results
