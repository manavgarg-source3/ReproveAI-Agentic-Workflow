"""Adapter from REPROVE schemas to the existing Scientometric engine."""

import os
import re
import sys
import unicodedata
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


def _parse_unnumbered_reference_fields(raw_reference: str) -> tuple[str | None, list[str]]:
    """Recover the author list and title from line-wrapped author-date citations."""

    value = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", raw_reference)).strip()
    protected = re.sub(
        r"\b([A-Z])\.\s+(?=[A-Z])",
        lambda match: f"{match.group(1)}\u0000 ",
        value,
    )
    parts = [part.replace("\u0000", ".").strip(" .") for part in re.split(r"\.\s+", protected)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None, []
    author_text, title = parts[0], parts[1]
    title = re.split(r"(?<=[?!])\s+", title, maxsplit=1)[0]
    title = re.sub(r",\s*(?:18|19|20)\d{2}[a-z]?$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"(?<=\w)-\s+(?=\w)", "", title)
    if not ("," in author_text or " and " in author_text):
        return None, []
    authors = [
        author.strip(" ,")
        for author in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", author_text)
        if author.strip(" ,")
    ]
    return title or None, authors


def _publication_year(raw_reference: str) -> int | None:
    """Return a visible publication year without mistaking arXiv IDs for years."""

    sanitized = re.sub(
        r"(?i)(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/\s*)\d{4}\.\s*\d+",
        " ",
        raw_reference,
    )
    sanitized = re.sub(r"(?i)10\.\d{4,9}/\s*\S+", " ", sanitized)
    candidates = re.findall(
        r"(?<!\d)((?:18|19|20)\d{2})(?:[a-z])?(?!\d|\.\d)",
        sanitized,
        flags=re.IGNORECASE,
    )
    return int(candidates[-1]) if candidates else None


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
        source = getattr(result, "metadata_source", "") or None
        normalized_doi = self._normalize_doi(getattr(result, "normalized_doi", "")) or None
        notes = [rationale] if rationale else []
        source_label = {
            "crossref": "Crossref",
            "openalex": "OpenAlex",
            "scopus": "Elsevier Scopus",
            "scopus_index": "Elsevier Scopus",
        }.get((source or "").lower(), source or "an external scholarly registry")
        if not reference.doi and status_value == "DOI_RECOVERED":
            notes.insert(0, f"The DOI was missing from the paper; {source_label} identified {normalized_doi} from matching bibliographic metadata.")
        elif not reference.doi and status_value == "DOI_RECOVERY_UNCERTAIN":
            notes.insert(0, f"The DOI was missing from the paper; {source_label} returned a plausible DOI candidate that requires human review.")
        elif not reference.doi and status_value in {"WORK_FOUND_NO_DOI", "SCOPUS_LINKED_NO_DOI"}:
            notes.insert(0, f"The paper supplied no DOI; {source_label} confirms a matching scholarly record, but no registered DOI was found.")
        elif not reference.doi and status_value in {"DOI_MISSING", "SCOPUS_UNLINKED"}:
            notes.insert(0, "The paper supplied no DOI, and Crossref, OpenAlex, and Elsevier Scopus produced no confident bibliographic match.")

        return ReferenceValidation(
            reference_id=reference.id,
            input_doi=reference.doi,
            normalized_doi=normalized_doi,
            doi_resolves=getattr(result, "doi_resolves", None),
            status=ReferenceValidationStatus(status_value),
            matched_title=getattr(result, "resolved_title", "") or None,
            matched_authors=_authors_list(getattr(result, "resolved_authors", "")),
            matched_year=getattr(result, "resolved_year", None),
            matched_venue=getattr(result, "resolved_journal", "") or None,
            metadata_match_score=getattr(result, "composite_score", None),
            source=source,
            confidence=confidence_value or None,
            needs_human_review=bool(getattr(result, "needs_human_review", False)),
            notes=notes,
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
        inferred_title, inferred_authors = (
            (numbered_title, numbered_authors)
            if numbered_title
            else _parse_unnumbered_reference_fields(raw_reference)
        )
        authors = inferred_authors or _authors_list(parsed.get("cited_authors", ""))
        doi_text = re.sub(r"(10\.\d{4,9}/)\s+", r"\1", raw_reference)
        doi_text = re.sub(
            r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\.\s+([A-Za-z0-9])",
            r"\1.\2",
            doi_text,
        )
        extracted_doi = extract_doi(doi_text)
        if extracted_doi:
            extracted_doi = re.sub(r"\.(?:URL|arXiv)$", "", extracted_doi, flags=re.IGNORECASE)
        references.append(Reference(
            id=f"ref_{index}",
            citation_text=raw_reference,
            title=inferred_title or parsed.get("cited_title") or None,
            authors=authors,
            year=_publication_year(raw_reference) or parsed.get("cited_year"),
            doi=extracted_doi,
        ))
    return references
