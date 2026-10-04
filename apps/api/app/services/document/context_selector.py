"""Priority-based section selection with an explicit bounded fallback."""

import re

from app.services.document.models import DocumentSection, SectionType, SelectedSection

HIGH_PRIORITY = {
    SectionType.ABSTRACT,
    SectionType.INTRODUCTION,
    SectionType.METHODS,
    SectionType.METHODOLOGY,
    SectionType.MODEL,
    SectionType.DATA,
    SectionType.DATASET,
    SectionType.EXPERIMENTS,
    SectionType.EXPERIMENTAL_SETUP,
    SectionType.RESULTS,
    SectionType.EVALUATION,
    SectionType.DISCUSSION,
    SectionType.CONCLUSION,
}
LOW_PRIORITY = {
    SectionType.RELATED_WORK,
    SectionType.BACKGROUND,
    SectionType.LIMITATIONS,
    SectionType.APPENDIX,
}


def _semantic_prefix(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    selected: list[str] = []
    used = 0
    for paragraph in paragraphs:
        addition = len(paragraph) + (2 if selected else 0)
        if used + addition > limit:
            break
        selected.append(paragraph)
        used += addition
    if selected:
        return "\n\n".join(selected)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if used + len(sentence) + 1 > limit:
            break
        selected.append(sentence.strip())
        used += len(sentence) + 1
    return " ".join(selected).strip()


def section_detection_is_reliable(sections: list[DocumentSection]) -> bool:
    substantive = [
        section for section in sections
        if section.section_type not in {SectionType.TITLE, SectionType.REFERENCES}
    ]
    return len(substantive) >= 2 and any(
        section.section_type in HIGH_PRIORITY for section in substantive
    )


def bounded_full_text_section(
    full_text: str,
    sections: list[DocumentSection],
    max_characters: int,
) -> SelectedSection:
    """Preserve semantic prefixes and a conclusion-sized tail when fallback is needed."""

    if len(full_text) <= max_characters:
        bounded = full_text
    else:
        head_budget = int(max_characters * 0.8)
        tail_budget = max_characters - head_budget
        head = _semantic_prefix(full_text, head_budget)
        tail_source = full_text[max(0, len(full_text) - tail_budget * 2):]
        tail_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", tail_source) if part.strip()]
        tail: list[str] = []
        used = 0
        for paragraph in reversed(tail_paragraphs):
            if used + len(paragraph) + 2 > tail_budget:
                continue
            tail.append(paragraph)
            used += len(paragraph) + 2
        bounded = f"{head}\n\n{''.join(reversed(tail))}".strip()
    base = sections[0] if sections else DocumentSection(
        section_id="section-fallback",
        title="Bounded full text",
        normalized_title="bounded_full_text",
        section_type=SectionType.OTHER,
        start_page=1,
        end_page=None,
        start_offset=0,
        end_offset=len(full_text),
        text=full_text,
    )
    fallback = DocumentSection(
        section_id="section-fallback",
        title="Bounded full text",
        normalized_title="bounded_full_text",
        section_type=SectionType.OTHER,
        start_page=base.start_page,
        end_page=(sections[-1].end_page if sections else base.end_page),
        start_offset=0,
        end_offset=len(full_text),
        text=bounded,
    )
    return SelectedSection(section=fallback, text=bounded, priority="FALLBACK")


def select_context(
    sections: list[DocumentSection],
    full_text: str,
    *,
    max_characters: int,
) -> tuple[list[SelectedSection], bool]:
    """Select high-value non-reference sections within the total context budget."""

    if not section_detection_is_reliable(sections):
        return [bounded_full_text_section(full_text, sections, max_characters)], True

    eligible = [section for section in sections if section.section_type != SectionType.REFERENCES]
    ranked = sorted(
        eligible,
        key=lambda section: (
            0 if section.section_type == SectionType.TITLE else
            1 if section.section_type in HIGH_PRIORITY else
            2 if section.section_type == SectionType.OTHER else 3,
            section.start_offset,
        ),
    )
    selected_by_id: dict[str, SelectedSection] = {}
    remaining = max_characters
    for section in ranked:
        if remaining <= 0:
            break
        # The title/authors preamble is useful but should not crowd out science.
        section_limit = min(4_000, remaining) if section.section_type == SectionType.TITLE else remaining
        selected_text = _semantic_prefix(section.text, section_limit)
        if not selected_text:
            continue
        priority = (
            "HIGH" if section.section_type in HIGH_PRIORITY or section.section_type == SectionType.TITLE
            else "LOW" if section.section_type in LOW_PRIORITY
            else "MEDIUM"
        )
        selected_by_id[section.section_id] = SelectedSection(
            section=section,
            text=selected_text,
            priority=priority,
        )
        remaining -= len(selected_text)

    return sorted(selected_by_id.values(), key=lambda item: item.section.start_offset), False
