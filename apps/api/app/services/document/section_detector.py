"""Conservative deterministic scientific-section detection."""

import re
from bisect import bisect_right

from app.services.document.models import DocumentSection, SectionType

NUMBERED_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+([A-Z][^.!?]{1,90})\s*$")
ROMAN_HEADING = re.compile(r"^\s*[IVXLC]+\.?\s+([A-Z][^.!?]{1,90})\s*$")

SPACED_SMALL_CAP_WORDS = {
    "A BSTRACT": "ABSTRACT",
    "B ACKGROUND": "BACKGROUND",
    "C ONCLUSION": "CONCLUSION",
    "C ONCLUSIONS": "CONCLUSIONS",
    "D ATA": "DATA",
    "D ATASET": "DATASET",
    "D ATASETS": "DATASETS",
    "D ISCUSSION": "DISCUSSION",
    "E VALUATION": "EVALUATION",
    "E XPERIMENT": "EXPERIMENT",
    "E XPERIMENTS": "EXPERIMENTS",
    "I MPLEMENTATION": "IMPLEMENTATION",
    "I NTRODUCTION": "INTRODUCTION",
    "L IMITATIONS": "LIMITATIONS",
    "M ETHOD": "METHOD",
    "M ETHODS": "METHODS",
    "M ETHODOLOGY": "METHODOLOGY",
    "R EFERENCES": "REFERENCES",
    "R ELATED": "RELATED",
    "R ESULT": "RESULT",
    "R ESULTS": "RESULTS",
}


def _repair_spaced_small_caps(title: str) -> str:
    value = title
    for broken, repaired in SPACED_SMALL_CAP_WORDS.items():
        value = re.sub(rf"\b{re.escape(broken)}\b", repaired, value, flags=re.IGNORECASE)
    return value


def normalize_heading(title: str) -> str:
    value = re.sub(r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+)\.?\s+", "", title.strip(), flags=re.IGNORECASE)
    value = _repair_spaced_small_caps(value)
    value = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return value


def classify_section(title: str) -> SectionType:
    normalized = normalize_heading(title)
    words = set(normalized.split("_"))
    if normalized in {"abstract", "summary"}:
        return SectionType.ABSTRACT
    if "introduction" in words:
        return SectionType.INTRODUCTION
    if normalized in {"related_work", "prior_work", "literature_review"} or {"related", "work"} <= words:
        return SectionType.RELATED_WORK
    if "background" in words:
        return SectionType.BACKGROUND
    if "methodology" in words:
        return SectionType.METHODOLOGY
    if {"dataset", "condensation"} <= words:
        return SectionType.METHODS
    if words & {"architecture", "model", "training"}:
        return SectionType.MODEL
    if "dataset" in words or "datasets" in words:
        return SectionType.DATASET
    if "data" in words:
        return SectionType.DATA
    if {"experimental", "setup"} <= words or {"experiment", "setup"} <= words:
        return SectionType.EXPERIMENTAL_SETUP
    if "experiment" in words or "experiments" in words:
        return SectionType.EXPERIMENTS
    if "evaluation" in words or "evaluations" in words:
        return SectionType.EVALUATION
    if "result" in words or "results" in words:
        return SectionType.RESULTS
    if "discussion" in words:
        return SectionType.DISCUSSION
    if "conclusion" in words or "conclusions" in words:
        return SectionType.CONCLUSION
    if "limitation" in words or "limitations" in words:
        return SectionType.LIMITATIONS
    if "appendix" in words or "appendices" in words:
        return SectionType.APPENDIX
    if words & {"references", "bibliography"} or normalized in {"works_cited", "reference_list"}:
        return SectionType.REFERENCES
    if words & {"method", "methods", "approach", "procedure"}:
        return SectionType.METHODS
    return SectionType.OTHER


def _known_unnumbered_heading(line: str) -> bool:
    normalized = normalize_heading(line)
    patterns = {
        "abstract", "summary", "introduction", "background", "related_work",
        "prior_work", "literature_review", "method", "methods", "methodology",
        "approach", "model_architecture", "model_architecture_and_training",
        "training_procedure", "data", "dataset", "datasets", "experiments",
        "experimental_setup", "experimental_results", "results",
        "results_and_discussion", "evaluation", "discussion",
        "discussion_and_conclusion", "conclusion", "conclusions", "limitations",
        "appendix", "appendices", "references", "bibliography", "works_cited",
        "reference_list",
    }
    return normalized in patterns


def is_heading_line(line: str, *, references_started: bool = False) -> bool:
    value = re.sub(r"\s+", " ", line).strip()
    if not value or len(value) > 100 or len(value.split()) > 12:
        return False
    if references_started:
        return False
    if re.match(r"^(?:table|figure|fig\.?|equation|eq\.?)\s*\d", value, re.IGNORECASE):
        return False
    if re.match(r"^(?:\[\d+]|\d+\.)\s+[A-Z][a-z]+,?\s+[A-Z]", value):
        return False
    if value.endswith(":" ) and _known_unnumbered_heading(value[:-1]):
        return True
    if value.endswith((".", ";", ",", ":")):
        return False
    numbered = NUMBERED_HEADING.match(value) or ROMAN_HEADING.match(value)
    if numbered:
        candidate = numbered.group(1).strip()
        return bool(candidate and len(candidate.split()) <= 10)
    return _known_unnumbered_heading(value)


def _page_boundaries(full_text: str, pages: tuple[str, ...]) -> tuple[list[int], list[int]]:
    starts: list[int] = []
    numbers: list[int] = []
    cursor = 0
    for number, page in enumerate(pages, start=1):
        clean = page.strip()
        if not clean:
            continue
        position = full_text.find(clean, cursor)
        if position < 0:
            position = cursor
        starts.append(position)
        numbers.append(number)
        cursor = position + len(clean)
    return starts, numbers


def _page_for_offset(offset: int, starts: list[int], numbers: list[int]) -> int | None:
    if not starts:
        return None
    index = max(0, bisect_right(starts, offset) - 1)
    return numbers[index]


def detect_sections(full_text: str, pages: tuple[str, ...] = ()) -> list[DocumentSection]:
    """Detect conservative boundaries while retaining full-text offsets and pages."""

    if not full_text.strip():
        return []
    headings: list[tuple[int, str, SectionType]] = []
    references_started = False
    offset = 0
    for raw_line in full_text.splitlines(keepends=True):
        line = raw_line.strip()
        if is_heading_line(line, references_started=references_started):
            section_type = classify_section(line)
            headings.append((offset + raw_line.find(line), line, section_type))
            if section_type == SectionType.REFERENCES:
                references_started = True
        offset += len(raw_line)

    page_starts, page_numbers = _page_boundaries(full_text, pages)
    boundaries: list[tuple[int, str, SectionType]] = []
    if not headings or headings[0][0] > 0:
        boundaries.append((0, "Document header", SectionType.TITLE))
    boundaries.extend(headings)

    sections: list[DocumentSection] = []
    for index, (start, title, section_type) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(full_text)
        text = full_text[start:end].strip()
        if not text:
            continue
        sections.append(DocumentSection(
            section_id=f"section-{len(sections) + 1:03d}",
            title=title,
            normalized_title=normalize_heading(title),
            section_type=section_type,
            start_page=_page_for_offset(start, page_starts, page_numbers),
            end_page=_page_for_offset(max(start, end - 1), page_starts, page_numbers),
            start_offset=start,
            end_offset=end,
            text=text,
        ))
    return sections
