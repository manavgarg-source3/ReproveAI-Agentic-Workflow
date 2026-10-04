"""Internal models for page-aware section selection and semantic chunks."""

from dataclasses import dataclass, field
from enum import Enum


class SectionType(str, Enum):
    TITLE = "TITLE"
    ABSTRACT = "ABSTRACT"
    INTRODUCTION = "INTRODUCTION"
    RELATED_WORK = "RELATED_WORK"
    BACKGROUND = "BACKGROUND"
    METHODS = "METHODS"
    METHODOLOGY = "METHODOLOGY"
    MODEL = "MODEL"
    DATA = "DATA"
    DATASET = "DATASET"
    EXPERIMENTS = "EXPERIMENTS"
    EXPERIMENTAL_SETUP = "EXPERIMENTAL_SETUP"
    RESULTS = "RESULTS"
    EVALUATION = "EVALUATION"
    DISCUSSION = "DISCUSSION"
    CONCLUSION = "CONCLUSION"
    LIMITATIONS = "LIMITATIONS"
    APPENDIX = "APPENDIX"
    REFERENCES = "REFERENCES"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class DocumentSection:
    section_id: str
    title: str
    normalized_title: str
    section_type: SectionType
    start_page: int | None
    end_page: int | None
    start_offset: int
    end_offset: int
    text: str


@dataclass(frozen=True, slots=True)
class SelectedSection:
    section: DocumentSection
    text: str
    priority: str


@dataclass(frozen=True, slots=True)
class ContextChunk:
    chunk_id: str
    text: str
    section_types: tuple[SectionType, ...]
    section_titles: tuple[str, ...]
    start_page: int | None
    end_page: int | None
    start_offset: int
    end_offset: int

    @property
    def character_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True, slots=True)
class PreprocessingDiagnostics:
    total_characters: int
    sections_detected: int
    selected_sections: tuple[str, ...]
    selected_characters: int
    chunks_created: int
    gemini_input_characters: int
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class PreparedDocumentContext:
    sections: tuple[DocumentSection, ...]
    selected_sections: tuple[SelectedSection, ...]
    chunks: tuple[ContextChunk, ...]
    diagnostics: PreprocessingDiagnostics
