"""Deterministic claim-to-citation mapping using the preserved engine parser."""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rapidfuzz.fuzz import token_set_ratio

from app.schemas.research import Claim, Reference
from app.services.scholarly.scientometric_adapter import _discover_engine_root


@dataclass(frozen=True)
class CitationAssociation:
    """One traceable link from a claim to an in-text marker and reference."""

    claim_id: str
    reference_id: str
    marker: str
    context_text: str
    location: str | None
    similarity: float


def _reference_number(reference: Reference, fallback: int) -> int:
    match = re.match(r"\s*\[(\d+)]", reference.citation_text)
    return int(match.group(1)) if match else fallback


def _surname(author: str) -> str:
    cleaned = re.sub(r"[^\w\-']+", " ", author, flags=re.UNICODE).strip()
    return cleaned.split()[-1].casefold() if cleaned else ""


def _author_year_keys(citation: dict[str, Any]) -> list[tuple[str, int]]:
    text = " ".join(
        str(citation.get(key, "")) for key in ("author", "year", "content", "marker")
    )
    years = [int(value) for value in re.findall(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", text)]
    authors = [
        value.casefold()
        for value in re.findall(r"\b([A-Z][A-Za-zÀ-ɏ\-']+)\b", text)
        if value.casefold() not in {"et", "al"}
    ]
    return [(author, year) for author in authors for year in years]


def _location_before(body: str, offset: int) -> str | None:
    """Return a nearby visible section heading without manufacturing a location."""

    lines = body[:offset].splitlines()
    numbered_heading = re.compile(
        r"^\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9 ,:&\-/]{2,70}$"
    )
    named_headings = {
        "abstract", "introduction", "background", "related work", "methods",
        "methodology", "experiments", "results", "discussion", "conclusion",
    }
    for line in reversed(lines[-80:]):
        candidate = re.sub(r"\s+", " ", line).strip()
        if (
            numbered_heading.match(candidate)
            or candidate.casefold() in named_headings
        ) and len(candidate.split()) <= 10:
            return candidate
    return None


class CitationMapper:
    """Reuse engine citation extraction and conservatively associate claim text."""

    def __init__(
        self,
        *,
        scanner: Callable[[str], tuple[Any, list[dict[str, Any]]]] | None = None,
        segmenter: Callable[[str], tuple[str, str, dict[str, Any]]] | None = None,
        minimum_similarity: float = 55.0,
    ) -> None:
        if scanner is None or segmenter is None:
            engine_root = Path(_discover_engine_root())
            engine_path = str(engine_root)
            if engine_path not in sys.path:
                sys.path.insert(0, engine_path)
            from src.parsing.citation_style_detector import CitationStyleDetector
            from src.parsing.section_segmenter import segment_manuscript

            scanner = scanner or CitationStyleDetector.scan_in_text_citations
            segmenter = segmenter or segment_manuscript
        self._scanner = scanner
        self._segmenter = segmenter
        self.minimum_similarity = minimum_similarity

    def map_claims(
        self,
        paper_text: str,
        claims: list[Claim],
        references: list[Reference],
    ) -> dict[str, list[CitationAssociation]]:
        """Map only sufficiently similar actual citation contexts to references."""

        body, _references_text, _metadata = self._segmenter(paper_text)
        _style, citations = self._scanner(body)
        numbered = {
            _reference_number(reference, index): reference
            for index, reference in enumerate(references, start=1)
        }
        mapped: dict[str, list[CitationAssociation]] = {claim.id: [] for claim in claims}

        for claim in claims:
            candidates: list[CitationAssociation] = []
            for citation in citations:
                context = str(citation.get("context", "")).strip()
                if not context:
                    continue
                similarity = float(token_set_ratio(claim.claim_text, context))
                if similarity < self.minimum_similarity:
                    continue

                matched_references: list[Reference] = []
                for number in citation.get("unrolled_keys", []):
                    reference = numbered.get(int(number))
                    if reference is not None:
                        matched_references.append(reference)

                if not matched_references:
                    keys = _author_year_keys(citation)
                    for reference in references:
                        surnames = {_surname(author) for author in reference.authors}
                        if reference.year is not None and any(
                            year == reference.year and author in surnames
                            for author, year in keys
                        ):
                            matched_references.append(reference)

                for reference in matched_references:
                    candidates.append(
                        CitationAssociation(
                            claim_id=claim.id,
                            reference_id=reference.id,
                            marker=str(citation.get("marker", "")).strip(),
                            context_text=context,
                            location=_location_before(body, int(citation.get("start", 0))),
                            similarity=similarity / 100.0,
                        )
                    )

            candidates.sort(key=lambda item: item.similarity, reverse=True)
            seen: set[tuple[str, str]] = set()
            for candidate in candidates:
                key = (candidate.reference_id, candidate.context_text)
                if key not in seen:
                    mapped[claim.id].append(candidate)
                    seen.add(key)
                if len(mapped[claim.id]) >= 3:
                    break
        return mapped
