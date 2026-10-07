"""Provider-neutral, section-aware research analysis and deterministic merge."""

import re
from dataclasses import dataclass

from rapidfuzz.fuzz import token_set_ratio

from app.schemas.research import Claim, Experiment, PaperMetadata, Reference, ResearchAnalysis
from app.services.document.models import ContextChunk, PreprocessingDiagnostics
from app.services.document.preprocessor import prepare_document_context
from app.services.llm.gemini import GeminiResearchProvider
from app.services.llm.provider import ResearchLLMProvider
from app.services.scholarly.scientometric_adapter import extract_references_from_document


@dataclass(frozen=True, slots=True)
class ResearchAnalysisRun:
    analysis: ResearchAnalysis
    diagnostics: PreprocessingDiagnostics


def _normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _chunk_location(chunk: ContextChunk) -> str:
    sections = ", ".join(dict.fromkeys(chunk.section_titles))
    if chunk.start_page and chunk.end_page:
        pages = f"page {chunk.start_page}" if chunk.start_page == chunk.end_page else f"pages {chunk.start_page}-{chunk.end_page}"
        return f"{sections}, {pages}"
    return sections


def _with_chunk_location(result: ResearchAnalysis, chunk: ContextChunk) -> ResearchAnalysis:
    location = _chunk_location(chunk)
    claims = [item if item.evidence_locations else item.model_copy(update={"evidence_locations": [location]}) for item in result.claims]
    experiments = [item if item.evidence_locations else item.model_copy(update={"evidence_locations": [location]}) for item in result.experiments]
    return result.model_copy(update={"claims": claims, "experiments": experiments})


def _same_claim(left: Claim, right: Claim) -> bool:
    if left.metric != right.metric or left.reported_value != right.reported_value:
        return False
    left_text, right_text = _normalized(left.claim_text), _normalized(right.claim_text)
    return left_text == right_text or token_set_ratio(left_text, right_text) >= 96.0


def _same_experiment(left: Experiment, right: Experiment) -> bool:
    # A baseline is comparison metadata, not part of the evaluated target's
    # identity.  Chunked extraction often names the baseline in one occurrence
    # and calls the same row "our method" in another.
    comparable = ("dataset", "split", "model", "metric", "reported_result")
    if any(
        getattr(left, field) is not None
        and getattr(right, field) is not None
        and _normalized(str(getattr(left, field))) != _normalized(str(getattr(right, field)))
        for field in comparable
    ):
        return False
    # Do not collapse otherwise-similar experiment descriptions that explicitly
    # use different images-per-class settings.
    setting_pattern = r"\b(\d+)\s+images?\s*(?:/|per)\s*class\b"
    left_setting = re.search(setting_pattern, left.objective, re.IGNORECASE)
    right_setting = re.search(setting_pattern, right.objective, re.IGNORECASE)
    if left_setting and right_setting and left_setting.group(1) != right_setting.group(1):
        return False
    shared_identity = any(
        getattr(left, field) is not None
        and getattr(right, field) is not None
        for field in ("dataset", "model", "metric")
    )
    if not shared_identity:
        return False
    left_text, right_text = _normalized(left.objective), _normalized(right.objective)
    return left_text == right_text or token_set_ratio(left_text, right_text) >= 92.0


def _merge_experiment(left: Experiment, right: Experiment) -> Experiment:
    updates = {
        field: getattr(left, field) if getattr(left, field) is not None else getattr(right, field)
        for field in ("dataset", "split", "model", "metric", "baseline", "reported_result")
    }
    updates["objective"] = max((left.objective, right.objective), key=len)
    updates["evidence_locations"] = _merge_locations(
        left.evidence_locations, right.evidence_locations
    )
    return left.model_copy(update=updates)


def _merge_locations(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def _same_author(left: str, right: str) -> bool:
    left_tokens = _normalized(left).split()
    right_tokens = _normalized(right).split()
    if left_tokens == right_tokens:
        return True
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False
    # A later chunk sometimes drops a middle initial. Merge only when the
    # visible first and last names agree and one form is a strict subset.
    return (
        left_tokens[0] == right_tokens[0]
        and left_tokens[-1] == right_tokens[-1]
        and (set(left_tokens) <= set(right_tokens) or set(right_tokens) <= set(left_tokens))
    )


def merge_research_analyses(analyses: list[ResearchAnalysis], *, deterministic_references: list[Reference] | None = None) -> ResearchAnalysis:
    """Conservatively merge chunk outputs and reassign collision-free stable IDs."""

    if not analyses:
        return ResearchAnalysis(paper=PaperMetadata())
    titles = [item.paper.title for item in analyses if item.paper.title]
    abstracts = [item.paper.abstract for item in analyses if item.paper.abstract]
    authors: list[str] = []
    for analysis in analyses:
        for author in analysis.paper.authors:
            if author and not any(_same_author(author, existing) for existing in authors):
                authors.append(author)
    years = [item.paper.year for item in analyses if item.paper.year is not None]
    paper = PaperMetadata(
        title=titles[0] if titles else None,
        authors=authors,
        year=years[0] if years else None,
        abstract=max(abstracts, key=len) if abstracts else None,
    )

    claims: list[Claim] = []
    for analysis in analyses:
        for candidate in analysis.claims:
            duplicate = next((item for item in claims if _same_claim(item, candidate)), None)
            if duplicate is None:
                claims.append(candidate)
            else:
                index = claims.index(duplicate)
                claims[index] = duplicate.model_copy(update={"evidence_locations": _merge_locations(duplicate.evidence_locations, candidate.evidence_locations)})
    claims = [item.model_copy(update={"id": f"claim_{index}"}) for index, item in enumerate(claims, start=1)]

    experiments: list[Experiment] = []
    for analysis in analyses:
        for candidate in analysis.experiments:
            duplicate = next((item for item in experiments if _same_experiment(item, candidate)), None)
            if duplicate is None:
                experiments.append(candidate)
            else:
                index = experiments.index(duplicate)
                experiments[index] = _merge_experiment(duplicate, candidate)
    experiments = [item.model_copy(update={"id": f"experiment_{index}"}) for index, item in enumerate(experiments, start=1)]

    methods: list[str] = []
    seen_methods: set[str] = set()
    for analysis in analyses:
        for method in analysis.methods:
            key = _normalized(method)
            if key and key not in seen_methods:
                methods.append(method)
                seen_methods.add(key)

    references = list(deterministic_references or [])
    if not references:
        seen_references: set[str] = set()
        for analysis in analyses:
            for reference in analysis.references:
                key = (reference.doi or _normalized(reference.citation_text)).casefold()
                if key and key not in seen_references:
                    references.append(reference)
                    seen_references.add(key)
        references = [item.model_copy(update={"id": f"ref_{index}"}) for index, item in enumerate(references, start=1)]

    return ResearchAnalysis(paper=paper, claims=claims, experiments=experiments, methods=methods, references=references)


def _enrich_explicit_global_protocols(
    analysis: ResearchAnalysis, text: str
) -> ResearchAnalysis:
    """Propagate an explicit global split statement to matching result records."""

    standard_train_test = bool(re.search(
        r"\b(?:use|using|used)\s+(?:the\s+)?standard\s+train\s*/\s*test\s+splits?\b",
        text,
        re.IGNORECASE,
    ))
    if not standard_train_test:
        return analysis
    experiments = []
    for experiment in analysis.experiments:
        result_text = f"{experiment.objective} {experiment.metric or ''}"
        if experiment.split is None and re.search(
            r"\b(?:test|testing)\b", result_text, re.IGNORECASE
        ):
            experiment = experiment.model_copy(update={"split": "test"})
        experiments.append(experiment)
    return analysis.model_copy(update={"experiments": experiments})


def analyze_research_document(text: str, pages: tuple[str, ...] = (), provider: ResearchLLMProvider | None = None) -> ResearchAnalysisRun:
    """Preprocess full text, analyze unique chunks, and merge with deterministic references."""

    prepared = prepare_document_context(text, pages)
    active_provider = provider or GeminiResearchProvider()
    outputs: list[ResearchAnalysis] = []
    seen_chunks: set[str] = set()
    try:
        for chunk in prepared.chunks:
            if chunk.text in seen_chunks:
                continue
            seen_chunks.add(chunk.text)
            outputs.append(_with_chunk_location(active_provider.analyze(chunk.text), chunk))
    finally:
        if provider is None:
            active_provider.close()

    deterministic_references = extract_references_from_document(text)
    merged = merge_research_analyses(
        outputs, deterministic_references=deterministic_references
    )
    return ResearchAnalysisRun(
        analysis=_enrich_explicit_global_protocols(merged, text),
        diagnostics=prepared.diagnostics,
    )


def analyze_research_text(text: str, provider: ResearchLLMProvider | None = None) -> ResearchAnalysis:
    """Backward-compatible short-text boundary returning the existing schema."""

    return analyze_research_document(text, (text,), provider).analysis
