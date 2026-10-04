"""Bounded source-text retrieval through providers already used by the engine."""

import html
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from app.schemas.research import Reference, ReferenceValidation
from app.services.evidence.provider import SourceEvidence
from app.services.scholarly.scientometric_adapter import _discover_engine_root

DEFAULT_MAX_SOURCE_CHARACTERS = 6_000


def _configured_limit() -> int:
    raw = os.getenv("MAX_SOURCE_EVIDENCE_CHARACTERS", str(DEFAULT_MAX_SOURCE_CHARACTERS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("MAX_SOURCE_EVIDENCE_CHARACTERS must be a positive integer.") from exc
    if value <= 0:
        raise ValueError("MAX_SOURCE_EVIDENCE_CHARACTERS must be a positive integer.")
    return value


def _clean_abstract(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    without_tags = re.sub(r"<[^>]+>", " ", value)
    cleaned = re.sub(r"\s+", " ", html.unescape(without_tags)).strip()
    return cleaned[:limit].rstrip() or None


def _openalex_abstract(inverted_index: Any, limit: int) -> str | None:
    if not isinstance(inverted_index, dict):
        return None
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        positioned.extend((position, str(word)) for position in positions if isinstance(position, int))
    text = " ".join(word for _position, word in sorted(positioned))
    return text[:limit].rstrip() or None


def _first_text(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0]).strip() or None
    if isinstance(value, str):
        return value.strip() or None
    return None


class ScientometricSourceEvidenceProvider:
    """Retrieve abstracts without fetching arbitrary publisher pages or bypassing access controls."""

    def __init__(
        self,
        *,
        crossref: Any | None = None,
        openalex: Any | None = None,
        max_characters: int | None = None,
    ) -> None:
        if crossref is None or openalex is None:
            engine_root = Path(_discover_engine_root())
            engine_path = str(engine_root)
            if engine_path not in sys.path:
                sys.path.insert(0, engine_path)
            from src.providers.crossref import CrossrefClient
            from src.providers.openalex import OpenAlexClient

            crossref = crossref or CrossrefClient()
            openalex = openalex or OpenAlexClient()
        self._crossref = crossref
        self._openalex = openalex
        self.max_characters = max_characters or _configured_limit()
        self._cache: dict[str, SourceEvidence] = {}

    def retrieve(
        self,
        reference: Reference,
        validation: ReferenceValidation | None,
    ) -> SourceEvidence:
        doi = (
            (validation.normalized_doi if validation is not None else None)
            or reference.doi
            or ""
        ).strip()
        if not doi:
            return SourceEvidence(
                reference_id=reference.id,
                source=validation.source if validation is not None else None,
                title=(validation.matched_title if validation is not None else None) or reference.title,
                locator=None,
                excerpt=None,
                evidence_type="UNAVAILABLE",
            )
        cached = self._cache.get(doi.casefold())
        if cached is not None:
            return SourceEvidence(
                reference_id=reference.id,
                source=cached.source,
                title=cached.title,
                locator=cached.locator,
                excerpt=cached.excerpt,
                evidence_type=cached.evidence_type,
            )

        crossref_work = self._crossref.get_work_details(doi) or {}
        crossref_excerpt = _clean_abstract(
            crossref_work.get("abstract"), self.max_characters
        )
        crossref_title = _first_text(crossref_work.get("title"))
        crossref_locator = _first_text(crossref_work.get("URL"))
        if crossref_excerpt:
            result = SourceEvidence(
                reference_id=reference.id,
                source="crossref",
                title=crossref_title or reference.title,
                locator=crossref_locator or f"https://doi.org/{doi}",
                excerpt=crossref_excerpt,
                evidence_type="ABSTRACT",
            )
            self._cache[doi.casefold()] = result
            return result

        # The preserved OpenAlex client normalizes metadata but does not expose its
        # abstract. This adapter uses the client's fixed-domain, rate-limited request
        # method and reconstructs only OpenAlex's bounded abstract inverted index.
        url = (
            f"{self._openalex.BASE_URL}/works/https://doi.org/"
            f"{urllib.parse.quote(doi)}"
        )
        openalex_work = self._openalex._request_with_retry(url) or {}
        openalex_excerpt = _openalex_abstract(
            openalex_work.get("abstract_inverted_index"), self.max_characters
        )
        primary_location = openalex_work.get("primary_location") or {}
        openalex_locator = primary_location.get("landing_page_url") or openalex_work.get("id")
        if openalex_excerpt:
            result = SourceEvidence(
                reference_id=reference.id,
                source="openalex",
                title=(openalex_work.get("display_name") or reference.title),
                locator=openalex_locator or f"https://doi.org/{doi}",
                excerpt=openalex_excerpt,
                evidence_type="ABSTRACT",
            )
        else:
            result = SourceEvidence(
                reference_id=reference.id,
                source=(validation.source if validation is not None else None),
                title=(validation.matched_title if validation is not None else None)
                or crossref_title
                or reference.title,
                locator=crossref_locator or openalex_locator or f"https://doi.org/{doi}",
                excerpt=None,
                evidence_type="METADATA_ONLY",
            )
        self._cache[doi.casefold()] = result
        return result
