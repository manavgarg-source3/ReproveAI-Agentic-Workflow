"""Semantic section/paragraph/sentence chunking with small bounded overlap."""

import re
from dataclasses import dataclass

from app.services.document.models import ContextChunk, SelectedSection, SectionType


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    section_type: SectionType
    title: str
    start_page: int | None
    end_page: int | None
    start_offset: int
    end_offset: int


def _split_large_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= limit:
            pieces.append(paragraph)
            continue
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", paragraph) if part.strip()]
        if len(sentences) > 1:
            buffer = ""
            for sentence in sentences:
                if buffer and len(buffer) + len(sentence) + 1 > limit:
                    pieces.append(buffer)
                    buffer = sentence
                else:
                    buffer = f"{buffer} {sentence}".strip()
            if buffer:
                pieces.append(buffer)
        else:
            # A malformed extraction can contain a single overlong line. Keep the
            # bound at a whitespace boundary as the final deterministic fallback.
            cursor = 0
            while cursor < len(paragraph):
                end = min(len(paragraph), cursor + limit)
                if end < len(paragraph):
                    boundary = paragraph.rfind(" ", cursor, end)
                    if boundary > cursor:
                        end = boundary
                pieces.append(paragraph[cursor:end].strip())
                cursor = end
    return [piece for piece in pieces if piece]


def _label(section: SelectedSection) -> str:
    pages = (
        f", pages {section.section.start_page}-{section.section.end_page}"
        if section.section.start_page and section.section.end_page and section.section.start_page != section.section.end_page
        else f", page {section.section.start_page}" if section.section.start_page else ""
    )
    return f"[{section.section.section_type.value}: {section.section.title}{pages}]"


def chunk_selected_sections(
    selected: list[SelectedSection],
    *,
    chunk_characters: int,
    overlap_characters: int,
) -> list[ContextChunk]:
    if chunk_characters <= 0 or overlap_characters < 0 or overlap_characters >= chunk_characters:
        raise ValueError("Chunk size must be positive and overlap must be smaller than the chunk.")
    units: list[_Unit] = []
    for item in selected:
        label = _label(item)
        content_limit = max(500, chunk_characters - len(label) - 2)
        cursor = 0
        for piece in _split_large_text(item.text, content_limit):
            relative = item.text.find(piece, cursor)
            if relative < 0:
                relative = cursor
            cursor = relative + len(piece)
            units.append(_Unit(
                text=f"{label}\n{piece}",
                section_type=item.section.section_type,
                title=item.section.title,
                start_page=item.section.start_page,
                end_page=item.section.end_page,
                start_offset=item.section.start_offset + relative,
                end_offset=item.section.start_offset + relative + len(piece),
            ))

    chunks: list[ContextChunk] = []
    current: list[_Unit] = []
    current_size = 0

    def flush() -> None:
        nonlocal current, current_size
        if not current:
            return
        chunks.append(ContextChunk(
            chunk_id=f"chunk-{len(chunks) + 1:03d}",
            text="\n\n".join(unit.text for unit in current),
            section_types=tuple(dict.fromkeys(unit.section_type for unit in current)),
            section_titles=tuple(dict.fromkeys(unit.title for unit in current)),
            start_page=next((unit.start_page for unit in current if unit.start_page is not None), None),
            end_page=next((unit.end_page for unit in reversed(current) if unit.end_page is not None), None),
            start_offset=min(unit.start_offset for unit in current),
            end_offset=max(unit.end_offset for unit in current),
        ))
        previous = current[-1]
        current = [previous] if overlap_characters and len(previous.text) <= overlap_characters else []
        current_size = len(previous.text) if current else 0

    for unit in units:
        addition = len(unit.text) + (2 if current else 0)
        if current and current_size + addition > chunk_characters:
            flush()
            addition = len(unit.text) + (2 if current else 0)
            if current and current_size + addition > chunk_characters:
                current = []
                current_size = 0
                addition = len(unit.text)
        current.append(unit)
        current_size += addition
    flush()
    return chunks
