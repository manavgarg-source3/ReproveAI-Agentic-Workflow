"""Configuration and orchestration for section-aware Gemini context."""

import os

from app.services.analysis_errors import AnalysisConfigurationError
from app.services.document.chunker import chunk_selected_sections
from app.services.document.context_selector import select_context
from app.services.document.models import PreparedDocumentContext, PreprocessingDiagnostics
from app.services.document.section_detector import detect_sections

DEFAULT_TOTAL_CONTEXT_CHARACTERS = 120_000
DEFAULT_GEMINI_INPUT_CHARACTERS = 45_000
DEFAULT_CHUNK_CHARACTERS = 40_000
DEFAULT_CHUNK_OVERLAP_CHARACTERS = 500


def _positive_integer(variable: str, default: int, *, allow_zero: bool = False) -> int:
    raw = os.getenv(variable)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise AnalysisConfigurationError(f"{variable} must be an integer.") from exc
    if value < 0 if allow_zero else value <= 0:
        qualifier = "non-negative" if allow_zero else "positive"
        raise AnalysisConfigurationError(f"{variable} must be {qualifier}.")
    return value


def prepare_document_context(
    full_text: str,
    pages: tuple[str, ...] = (),
    *,
    total_context_characters: int | None = None,
    gemini_input_characters: int | None = None,
    chunk_characters: int | None = None,
    overlap_characters: int | None = None,
) -> PreparedDocumentContext:
    """Detect, prioritize, bound, and chunk while retaining full-text trace metadata."""

    total_limit = total_context_characters or _positive_integer(
        "MAX_ANALYSIS_CHARACTERS", DEFAULT_TOTAL_CONTEXT_CHARACTERS
    )
    input_limit = gemini_input_characters or _positive_integer(
        "GEMINI_MAX_INPUT_CHARS", DEFAULT_GEMINI_INPUT_CHARACTERS
    )
    target_chunk = chunk_characters or _positive_integer(
        "GEMINI_CHUNK_CHARS", DEFAULT_CHUNK_CHARACTERS
    )
    overlap = overlap_characters if overlap_characters is not None else _positive_integer(
        "GEMINI_CHUNK_OVERLAP_CHARS", DEFAULT_CHUNK_OVERLAP_CHARACTERS, allow_zero=True
    )
    effective_chunk = min(target_chunk, input_limit)
    if overlap >= effective_chunk:
        raise AnalysisConfigurationError(
            "GEMINI_CHUNK_OVERLAP_CHARS must be smaller than the effective chunk size."
        )

    sections = detect_sections(full_text, pages)
    selected, fallback = select_context(
        sections,
        full_text,
        max_characters=total_limit,
    )
    chunks = chunk_selected_sections(
        selected,
        chunk_characters=effective_chunk,
        overlap_characters=overlap,
    )
    if not chunks:
        raise AnalysisConfigurationError("Document preprocessing produced no Gemini context.")

    selected_characters = sum(len(item.text) for item in selected)
    diagnostics = PreprocessingDiagnostics(
        total_characters=len(full_text),
        sections_detected=len(sections),
        selected_sections=tuple(item.section.section_type.value for item in selected),
        selected_characters=selected_characters,
        chunks_created=len(chunks),
        gemini_input_characters=sum(chunk.character_count for chunk in chunks),
        fallback_used=fallback,
    )
    return PreparedDocumentContext(
        sections=tuple(sections),
        selected_sections=tuple(selected),
        chunks=tuple(chunks),
        diagnostics=diagnostics,
    )
