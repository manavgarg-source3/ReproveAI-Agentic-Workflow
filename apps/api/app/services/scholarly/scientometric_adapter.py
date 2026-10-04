"""Adapter from REPROVE schemas to the existing Scientometric engine."""

import os
import re
import sys
from pathlib import Path
from typing import Any

from app.schemas.research import (
    Reference,
    ReferenceValidation,
    ReferenceValidationStatus,
)


class ScientometricAdapterConfigurationError(RuntimeError):
    """Raised when the existing engine cannot be located or imported."""


def _ensure_engine_path() -> Path:
    engine_root = _discover_engine_root()
    if not (engine_root / "src").is_dir():
        raise ScientometricAdapterConfigurationError(
            f"Scientometric engine was not found at {engine_root}."
        )
    engine_path = str(engine_root)
    if engine_path not in sys.path:
        sys.path.insert(0, engine_path)
    return engine_root


def _discover_engine_root() -> Path:
    configured = os.getenv("SCIENTOMETRIC_ENGINE_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    current_file = Path(__file__).resolve()
    workspace_root = next(
        (parent for parent in current_file.parents if (parent / "apps" / "api").is_dir()),
        None,
    )
    if workspace_root is None:
        raise ScientometricAdapterConfigurationError(
            "Could not discover the REPROVE workspace root."
        )
    return workspace_root / "Scientometric-Audit-Studio-main"


def _authors_list(raw_authors: Any) -> list[str]:
    if not raw_authors:
        return []
    if isinstance(raw_authors, list):
        return [str(author).strip() for author in raw_authors if str(author).strip()]
    return [part.strip() for part in str(raw_authors).split(";") if part.strip()]


def _parse_numbered_reference_fields(raw_reference: str) -> tuple[str | None, list[str]]:
    """Recover author/title fields from common bracket-key scientific citations.

    The preserved engine parser is deliberately broad, but on references shaped
    as ``[n] Authors. Title. Venue.`` it can retain the final author in the
    title.  This narrow adapter-side correction improves the metadata supplied
    to that engine without modifying its source or guessing beyond visible text.
    """

    if not re.match(r"\s*\[(?:\d+|[A-Za-z][A-Za-z0-9+]*\d{2}[a-z]?)\]", raw_reference):
        return None, []

    value = re.sub(r"\s+", " ", raw_reference).strip()
    value = re.sub(r"\s+\.\s+", ". ", value)
    value = re.sub(
        r"^\s*\[(?:\d+|[A-Za-z][A-Za-z0-9+]*\d{2}[a-z]?)\]\s*",
        "",
        value,
    )

    # Do not interpret initials such as "A. Smith" as sentence boundaries.
    protected = re.sub(
        r"\b([A-Z])\.\s+(?=[A-ZÀ-ÖØ-Þ])",
        lambda match: f"{match.group(1)}\u0000 ",
        value,
    )
    parts = [part.replace("\u0000", ".").strip(" .") for part in re.split(r"\.\s+", protected)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None, []

    author_text, title = parts[0], parts[1]
    authors = [
        author.strip(" ,")
        for author in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", author_text)
        if author.strip(" ,")
    ]
    return title or None, authors


class ScientometricAdapter:
    """Keep all engine-specific imports and translations behind one boundary."""

    def __init__(
        self,
        *,
        validator: Any | None = None,
        parsed_reference_type: Any | None = None,
        citation_parser: Any | None = None,
        normalize_doi_fn: Any | None = None,
    ) -> None:
        if validator is not None and parsed_reference_type is not None:
            self._validator = validator
            self._parsed_reference_type = parsed_reference_type
            self._citation_parser = citation_parser
            self._normalize_doi = normalize_doi_fn or (lambda value: value)
            return

        engine_root = _ensure_engine_path()
        if not (engine_root / "src" / "validation" / "doi_validator.py").is_file():
            raise ScientometricAdapterConfigurationError(
                f"Scientometric engine was not found at {engine_root}."
            )

        try:
            import config as engine_config
            from src.models.reference import ParsedReference
            from src.parsing.citation_parser import CitationParser
            from src.parsing.doi_extractor import normalize_doi
            from src.validation.doi_validator import ReferenceValidator
        except ImportError as exc:
            raise ScientometricAdapterConfigurationError(
                "Scientometric engine dependencies could not be imported."
            ) from exc

        # STEP 1C must remain deterministic even if the standalone engine has an
        # optional LLM parsing fallback enabled in its own runtime configuration.
        engine_config.ENABLE_LLM_FALLBACK = False
        self._validator = ReferenceValidator()
        self._parsed_reference_type = ParsedReference
        self._citation_parser = CitationParser
        self._normalize_doi = normalize_doi

    def validate_reference(self, reference: Reference) -> ReferenceValidation:
        """Translate, validate with the engine, and map the result to Pydantic."""

        parsed = (
            self._citation_parser.parse(reference.citation_text)
            if self._citation_parser is not None
            else {}
        )
        input_doi = reference.doi or ""
        normalized_input_doi = self._normalize_doi(input_doi) if input_doi else None
        engine_reference = self._parsed_reference_type(
            source_eid="reprove",
            reference_no=0,
            raw_reference=reference.citation_text,
            cited_title=reference.title or parsed.get("cited_title", ""),
            cited_authors="; ".join(reference.authors) or parsed.get("cited_authors", ""),
            cited_year=reference.year or parsed.get("cited_year"),
            cited_journal=parsed.get("cited_journal", ""),
            cited_volume=parsed.get("cited_volume", ""),
            cited_issue=parsed.get("cited_issue", ""),
            cited_pages=parsed.get("cited_pages", ""),
            extracted_doi=normalized_input_doi or input_doi,
            has_doi=bool(reference.doi),
            has_year=reference.year is not None,
        )
        result = self._validator.validate_reference(engine_reference)

        status_value = getattr(result.final_status, "value", str(result.final_status))
        confidence_value = getattr(result.confidence, "value", str(result.confidence))
        rationale = str(getattr(result, "decision_rationale", "")).strip()

        return ReferenceValidation(
            reference_id=reference.id,
            input_doi=reference.doi,
            normalized_doi=(
                self._normalize_doi(getattr(result, "normalized_doi", "")) or None
            ),
            doi_resolves=getattr(result, "doi_resolves", None),
            status=ReferenceValidationStatus(status_value),
            matched_title=getattr(result, "resolved_title", "") or None,
            matched_authors=_authors_list(getattr(result, "resolved_authors", "")),
            matched_year=getattr(result, "resolved_year", None),
            matched_venue=getattr(result, "resolved_journal", "") or None,
            metadata_match_score=getattr(result, "composite_score", None),
            source=getattr(result, "metadata_source", "") or None,
            confidence=confidence_value or None,
            needs_human_review=bool(getattr(result, "needs_human_review", False)),
            notes=[rationale] if rationale else [],
        )


def extract_references_from_document(text: str) -> list[Reference]:
    """Reuse engine segmentation/parsing so references need not consume LLM context."""

    _ensure_engine_path()
    try:
        from src.parsing.citation_parser import CitationParser
        from src.parsing.doi_extractor import extract_doi
        from src.parsing.reference_splitter import ReferenceSplitter
        from src.parsing.section_segmenter import segment_manuscript
    except ImportError as exc:
        raise ScientometricAdapterConfigurationError(
            "Scientometric reference parsing dependencies could not be imported."
        ) from exc

    _body, references_text, metadata = segment_manuscript(text)
    if not metadata.get("found_references_heading") and metadata.get("fallback_used") == "none":
        return []
    author_year_markers = list(
        re.finditer(
            r"(?<!\w)\[[A-Za-z][A-Za-z0-9+]*\d{2}[a-z]?\]\s+",
            references_text,
        )
    )
    if len(author_year_markers) >= 5:
        raw_references = []
        for index, marker in enumerate(author_year_markers):
            end = (
                author_year_markers[index + 1].start()
                if index + 1 < len(author_year_markers)
                else None
            )
            raw_reference = references_text[marker.start() : end].strip()
            if raw_reference:
                raw_references.append(raw_reference)
    else:
        raw_references = ReferenceSplitter.split_manuscript_references(references_text)
    numbered_count = sum(
        1 for raw_reference in raw_references
        if re.match(r"\s*\[\d+]", raw_reference)
    )
    if numbered_count >= max(2, len(raw_references) // 2):
        raw_references = [
            raw_reference for raw_reference in raw_references
            if re.match(r"\s*\[\d+]", raw_reference)
        ]
    references: list[Reference] = []
    for index, raw_reference in enumerate(raw_references, start=1):
        parsed = CitationParser.parse(raw_reference)
        numbered_title, numbered_authors = _parse_numbered_reference_fields(raw_reference)
        authors = numbered_authors or _authors_list(parsed.get("cited_authors", ""))
        references.append(Reference(
            id=f"ref_{index}",
            citation_text=raw_reference,
            title=numbered_title or parsed.get("cited_title") or None,
            authors=authors,
            year=parsed.get("cited_year"),
            doi=extract_doi(raw_reference),
        ))
    return references
