"""Step 1D deterministic preprocessing, chunking, and merge tests."""

from app.schemas.research import Claim, Experiment, PaperMetadata, ResearchAnalysis
from app.services.analyzer import analyze_research_document, merge_research_analyses
from app.services.document.chunker import chunk_selected_sections
from app.services.document.context_selector import select_context
from app.services.document.preprocessor import prepare_document_context
from app.services.document.section_detector import (
    classify_section,
    detect_sections,
    is_heading_line,
)
from app.services.document.models import SectionType


STRUCTURED_TEXT = """A Study of Reliable Models
Ada Researcher

Abstract
We report a controlled result of 91 percent accuracy.

1 Introduction
This work introduces the research question and its motivation.

2 Methods
We train Model-X with a documented optimization procedure.

3 Experimental Setup
Dataset-Y is divided into training and test splits.

4 Results
Model-X reaches 91 percent accuracy on Dataset-Y. Table 2 reports the comparison.

5 Conclusion
The paper concludes that Model-X improves the measured result.

References
[1] A. Author. Prior Study. 2020.
"""


def test_heading_detection_finds_numbered_and_named_sections() -> None:
    sections = detect_sections(STRUCTURED_TEXT)
    types = [section.section_type for section in sections]
    assert SectionType.ABSTRACT in types
    assert SectionType.METHODS in types
    assert SectionType.EXPERIMENTAL_SETUP in types
    assert SectionType.RESULTS in types
    assert SectionType.REFERENCES in types


def test_section_classification_handles_non_exact_titles() -> None:
    assert classify_section("4. Experimental Results") == SectionType.RESULTS
    assert classify_section("Results and Discussion") == SectionType.RESULTS
    assert classify_section("Model Architecture and Training") == SectionType.MODEL
    assert classify_section("Literature Review") == SectionType.RELATED_WORK
    assert classify_section("2.3 D ATASET CONDENSATION WITH GRADIENT MATCHING") == SectionType.METHODS
    assert classify_section("3 E XPERIMENTS") == SectionType.EXPERIMENTS
    assert classify_section("4 R ESULTS AND DISCUSSION") == SectionType.RESULTS


def test_false_heading_rejection_for_tables_captions_authors_and_references() -> None:
    assert not is_heading_line("Table 2 Accuracy BLEU")
    assert not is_heading_line("Figure 3. Model architecture")
    assert not is_heading_line("[12] Smith J. Example Paper")
    assert not is_heading_line("The result improves significantly.")
    assert not is_heading_line("Ada Researcher, Bob Scientist")
    assert not is_heading_line("Experiments on two tasks show these models improve quality")
    assert not is_heading_line("Our model establishes a new state-of-the-art result")


def test_detected_sections_preserve_page_ranges() -> None:
    pages = (
        "A Study\n\nAbstract\nSummary text.\n\n1 Introduction\nIntro text.",
        "2 Methods\nMethod text.\n\n3 Results\nResult text.",
        "4 Conclusion\nConclusion text.\n\nReferences\n[1] A. Author. Work.",
    )
    text = "\n\n".join(pages)
    sections = detect_sections(text, pages)
    methods = next(item for item in sections if item.section_type == SectionType.METHODS)
    conclusion = next(item for item in sections if item.section_type == SectionType.CONCLUSION)
    assert methods.start_page == 2
    assert conclusion.start_page == 3


def test_context_selection_prioritizes_relevant_sections() -> None:
    sections = detect_sections(STRUCTURED_TEXT)
    selected, fallback = select_context(sections, STRUCTURED_TEXT, max_characters=10_000)
    selected_types = {item.section.section_type for item in selected}
    assert fallback is False
    assert {SectionType.ABSTRACT, SectionType.METHODS, SectionType.RESULTS} <= selected_types


def test_references_are_excluded_from_main_analysis_context() -> None:
    sections = detect_sections(STRUCTURED_TEXT)
    selected, _fallback = select_context(sections, STRUCTURED_TEXT, max_characters=10_000)
    assert SectionType.REFERENCES not in {item.section.section_type for item in selected}
    assert "Prior Study" not in "\n".join(item.text for item in selected)


def test_selected_context_respects_total_character_bound() -> None:
    long_text = STRUCTURED_TEXT.replace(
        "This work introduces the research question and its motivation.",
        "Introduction evidence sentence.\n\n" * 100,
    )
    prepared = prepare_document_context(
        long_text,
        total_context_characters=1_200,
        gemini_input_characters=600,
        chunk_characters=500,
        overlap_characters=50,
    )
    assert prepared.diagnostics.selected_characters <= 1_200
    assert all(chunk.character_count <= 600 for chunk in prepared.chunks)


def test_chunking_preserves_complete_paragraphs_when_they_fit() -> None:
    sections = detect_sections(STRUCTURED_TEXT)
    selected, _fallback = select_context(sections, STRUCTURED_TEXT, max_characters=10_000)
    chunks = chunk_selected_sections(selected, chunk_characters=350, overlap_characters=0)
    combined = "\n".join(chunk.text for chunk in chunks)
    assert "Dataset-Y is divided into training and test splits." in combined
    assert "Table 2 reports the comparison." in combined


class RecordingProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.inputs = []
        self.closed = False

    def analyze(self, text):
        self.inputs.append(text)
        return self.outputs[min(len(self.inputs) - 1, len(self.outputs) - 1)]

    def close(self):
        self.closed = True


def test_multi_chunk_processing_calls_provider_once_per_unique_chunk(monkeypatch) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_CHARACTERS", "10000")
    monkeypatch.setenv("GEMINI_MAX_INPUT_CHARS", "350")
    monkeypatch.setenv("GEMINI_CHUNK_CHARS", "300")
    monkeypatch.setenv("GEMINI_CHUNK_OVERLAP_CHARS", "0")
    monkeypatch.setattr("app.services.analyzer.extract_references_from_document", lambda _text: [])
    provider = RecordingProvider([
        ResearchAnalysis(paper=PaperMetadata(title="A Study"), methods=["Method A"]),
        ResearchAnalysis(paper=PaperMetadata(title="A Study"), methods=["Method B"]),
    ])
    run = analyze_research_document(STRUCTURED_TEXT, provider=provider)
    assert len(provider.inputs) > 1
    assert {"Method A", "Method B"} <= set(run.analysis.methods)


def test_deterministic_merge_preserves_distinct_outputs() -> None:
    first = ResearchAnalysis(
        paper=PaperMetadata(title="Paper", authors=["Ada"]),
        claims=[Claim(id="c1", claim_text="Accuracy improves.", claim_type="PERFORMANCE", metric="accuracy", reported_value=0.91)],
        methods=["Method A"],
    )
    second = ResearchAnalysis(
        paper=PaperMetadata(title="Paper", authors=["Bob"]),
        claims=[Claim(id="c2", claim_text="Latency decreases.", claim_type="PERFORMANCE", metric="latency", reported_value=10)],
        methods=["Method B"],
    )
    merged = merge_research_analyses([first, second])
    assert len(merged.claims) == 2
    assert merged.paper.authors == ["Ada", "Bob"]
    assert merged.methods == ["Method A", "Method B"]


def test_deterministic_merge_deduplicates_author_middle_initial_variants() -> None:
    first = ResearchAnalysis(
        paper=PaperMetadata(authors=["Tom B. Brown", "Daniel M. Ziegler"])
    )
    second = ResearchAnalysis(
        paper=PaperMetadata(authors=["Tom Brown", "Daniel M Ziegler"])
    )

    merged = merge_research_analyses([first, second])

    assert merged.paper.authors == ["Tom B. Brown", "Daniel M. Ziegler"]


def test_duplicate_claims_merge_locations_without_collapsing_different_values() -> None:
    base = dict(id="c", claim_text="The model reaches 91 percent accuracy.", claim_type="PERFORMANCE", metric="accuracy")
    first = ResearchAnalysis(paper=PaperMetadata(), claims=[Claim(**base, reported_value=0.91, evidence_locations=["Abstract"])])
    duplicate = ResearchAnalysis(paper=PaperMetadata(), claims=[Claim(**base, reported_value=0.91, evidence_locations=["Results"])])
    different = ResearchAnalysis(paper=PaperMetadata(), claims=[Claim(**base, reported_value=0.92, evidence_locations=["Table 2"])])
    merged = merge_research_analyses([first, duplicate, different])
    assert len(merged.claims) == 2
    assert merged.claims[0].evidence_locations == ["Abstract", "Results"]


def test_duplicate_experiments_merge_deterministically() -> None:
    experiment = dict(objective="Evaluate Model-X", dataset="Dataset-Y", model="Model-X", metric="accuracy", reported_result=0.91)
    first = ResearchAnalysis(paper=PaperMetadata(), experiments=[Experiment(id="e1", **experiment, evidence_locations=["Setup"])])
    second = ResearchAnalysis(paper=PaperMetadata(), experiments=[Experiment(id="e2", **experiment, evidence_locations=["Results"])])
    merged = merge_research_analyses([first, second])
    assert len(merged.experiments) == 1
    assert merged.experiments[0].id == "experiment_1"
    assert merged.experiments[0].evidence_locations == ["Setup", "Results"]


def test_poor_section_detection_uses_bounded_full_text_fallback() -> None:
    text = "A short unstructured paper paragraph. " * 200
    prepared = prepare_document_context(
        text,
        total_context_characters=700,
        gemini_input_characters=500,
        chunk_characters=450,
        overlap_characters=0,
    )
    assert prepared.diagnostics.fallback_used is True
    assert prepared.diagnostics.selected_characters <= 700


def test_missing_evidence_locations_receive_detected_section_and_page(monkeypatch) -> None:
    monkeypatch.setattr("app.services.analyzer.extract_references_from_document", lambda _text: [])
    provider = RecordingProvider([ResearchAnalysis(
        paper=PaperMetadata(title="A Study"),
        claims=[Claim(id="c1", claim_text="The model improves.", claim_type="PERFORMANCE")],
    )])
    run = analyze_research_document(STRUCTURED_TEXT, (STRUCTURED_TEXT,), provider)
    assert run.analysis.claims[0].evidence_locations
    assert "page 1" in run.analysis.claims[0].evidence_locations[0]


def test_old_short_unstructured_paper_still_analyzes(monkeypatch) -> None:
    monkeypatch.setattr("app.services.analyzer.extract_references_from_document", lambda _text: [])
    provider = RecordingProvider([ResearchAnalysis(paper=PaperMetadata(title="Short Paper"))])
    run = analyze_research_document("Short paper body.", provider=provider)
    assert run.analysis.paper.title == "Short Paper"
    assert run.diagnostics.fallback_used is True
    assert len(provider.inputs) == 1


def test_long_paper_input_is_bounded_and_chunked() -> None:
    long_results = "Result paragraph reports metric values without truncating a sentence.\n\n" * 500
    text = STRUCTURED_TEXT.replace("Model-X reaches 91 percent accuracy on Dataset-Y. Table 2 reports the comparison.", long_results)
    prepared = prepare_document_context(
        text,
        total_context_characters=8_000,
        gemini_input_characters=1_500,
        chunk_characters=1_200,
        overlap_characters=100,
    )
    assert prepared.diagnostics.total_characters > 20_000
    assert prepared.diagnostics.selected_characters <= 8_000
    assert prepared.diagnostics.chunks_created > 1
    assert max(chunk.character_count for chunk in prepared.chunks) <= 1_500
