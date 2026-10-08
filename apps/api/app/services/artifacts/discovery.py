"""Deterministic, non-executing artifact discovery from paper text and public metadata."""

import re
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field

from rapidfuzz.fuzz import token_set_ratio

from app.schemas.research import (
    Artifact,
    ArtifactConfidence,
    ArtifactDiscoveryMethod,
    ArtifactStatus,
    ArtifactType,
    Experiment,
    ResearchAnalysis,
)
from app.services.artifacts.provider import RepositoryMetadata, RepositoryMetadataProvider
from app.services.artifacts.repository import (
    PublicRepositoryMetadataProvider,
    normalize_repository_url,
    parse_repository_url,
)

URL_PATTERN = re.compile(
    r"(?:"
    r"(?:https?://|www\.)[^\s<>{}\[\]\"']+"
    r"|(?<![\w./])(?:github|gitlab)\.com/[^\s<>{}\[\]\"']+"
    r")",
    re.IGNORECASE,
)
TRAILING_URL_PUNCTUATION = ".,;:!?)]}>'\""
WRAPPED_URL_PATH = re.compile(
    r"[ \t]*\r?\n[ \t]*([A-Za-z0-9][A-Za-z0-9._~!$&'()*+,;=:@%/-]*)"
)


@dataclass
class _Candidate:
    type: ArtifactType
    name: str | None
    source_url: str | None
    discovery_method: ArtifactDiscoveryMethod
    context: str
    evidence_location: str | None
    experiment_id: str | None = None
    identifier: str | None = None
    repository: str | None = None
    source: str | None = None
    relationship_status: ArtifactStatus = ArtifactStatus.FOUND
    availability_status: ArtifactStatus = ArtifactStatus.FOUND
    confidence: ArtifactConfidence = ArtifactConfidence.MEDIUM
    description: str | None = None
    version: str | None = None
    commit: str | None = None
    notes: list[str] = field(default_factory=list)


def normalize_public_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip(TRAILING_URL_PUNCTUATION)
    if re.match(r"^(?:github|gitlab)\.com/", value, re.IGNORECASE):
        value = f"https://{value}"
    elif value.casefold().startswith("www."):
        value = f"https://{value}"
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) artifact URLs are supported.")
    scheme = parsed.scheme.casefold()
    host = parsed.hostname.casefold()
    port = f":{parsed.port}" if parsed.port else ""
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    return urllib.parse.urlunsplit((scheme, f"{host}{port}", path, parsed.query, ""))


def _context(text: str, start: int, end: int, window: int = 240) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - window):min(len(text), end + window)]).strip()


def _url_candidates(text: str) -> Iterator[tuple[str, int, int]]:
    """Yield URLs while repairing PDF line wraps immediately after a slash.

    PDF text extraction commonly turns ``host/owner/repo`` into
    ``host/\nowner/repo``. Continuation is deliberately limited to URLs whose
    current fragment ends in a slash so adjacent prose is not absorbed.
    """

    for match in URL_PATTERN.finditer(text):
        raw_url = match.group(0)
        end = match.end()
        while raw_url.endswith("/"):
            continuation = WRAPPED_URL_PATH.match(text, end)
            if continuation is None:
                break
            raw_url += continuation.group(1)
            end = continuation.end()
        yield raw_url, match.start(), end


def _location_before(text: str, offset: int) -> str | None:
    numbered = re.compile(r"^\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9 ,:&\-/]{2,70}$")
    named = {"abstract", "introduction", "methods", "experiments", "results", "discussion", "conclusion", "appendix"}
    for line in reversed(text[:offset].splitlines()):
        candidate = re.sub(r"\s+", " ", line).strip()
        if (numbered.match(candidate) or candidate.casefold() in named) and len(candidate.split()) <= 10:
            return candidate
    return None


def _classify_url(url: str, context: str) -> ArtifactType | None:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    path = parsed.path.casefold()

    paper_domains = {
        "arxiv.org", "www.arxiv.org",
        "aclanthology.org", "www.aclanthology.org",
        "doi.org", "www.doi.org",
        "dl.acm.org", "ieeexplore.ieee.org",
        "proceedings.mlr.press", "neurips.cc"
    }
    if hostname in paper_domains:
        return None

    lowered = f"{url} {context}".casefold()
    filename = path.rsplit("/", 1)[-1]
    if filename in {"requirements.txt", "pyproject.toml", "setup.py", "environment.yml", "environment.yaml", "package.json"}:
        return ArtifactType.DEPENDENCY
    if filename in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"} or "hub.docker.com" in lowered:
        return ArtifactType.CONTAINER
    if filename.endswith((".sh", ".bash")) or filename in {"train.py", "evaluate.py", "eval.py", "run.py"}:
        return ArtifactType.EXECUTION_SCRIPT
    if filename.endswith((".yaml", ".yml", ".toml", ".ini", ".cfg", ".json")) and "dataset" not in lowered:
        return ArtifactType.CONFIG
    if filename.endswith((".ckpt", ".pth", ".pt", ".safetensors", ".bin")):
        return ArtifactType.CHECKPOINT
    try:
        parse_repository_url(url)
        return ArtifactType.CODE
    except ValueError:
        pass
    if "huggingface.co/datasets/" in lowered or "kaggle.com/datasets/" in lowered or re.search(r"\b(dataset|corpus|benchmark data)\b", context, re.IGNORECASE):
        return ArtifactType.DATASET
    if "huggingface.co/" in lowered or re.search(r"\b(model weights?|pretrained model|checkpoint)\b", context, re.IGNORECASE):
        return ArtifactType.MODEL
    if re.search(r"\b(supplementary|supplemental|appendix material)\b", context, re.IGNORECASE):
        return ArtifactType.SUPPLEMENTARY
    if re.search(r"\b(source code|code (?:is )?available|implementation|repository)\b", context, re.IGNORECASE):
        return ArtifactType.CODE
    return None


def _associate_experiment(context: str, experiments: list[Experiment]) -> str | None:
    best_id = None
    best_score = 0.0
    for experiment in experiments:
        # Repository links may sit near a broad method discussion shared by many
        # experiments. Only dataset/model identity is discriminative enough for
        # direct association; objectives and generic metrics create false links.
        terms = [experiment.dataset, experiment.model]
        score = max(
            (token_set_ratio(term, context) for term in terms if term and len(term) >= 3),
            default=0.0,
        )
        if score > best_score:
            best_score = score
            best_id = experiment.id
    return best_id if best_score >= 80.0 else None


def _repository_relationship(
    candidate: _Candidate,
    metadata: RepositoryMetadata,
    analysis: ResearchAnalysis,
) -> None:
    candidate.source = metadata.platform
    candidate.name = metadata.name
    candidate.repository = metadata.canonical_url
    candidate.description = metadata.description
    candidate.commit = metadata.latest_commit
    if not metadata.accessible:
        candidate.availability_status = ArtifactStatus.INACCESSIBLE
        candidate.relationship_status = ArtifactStatus.PARTIAL
        candidate.confidence = ArtifactConfidence.LOW
        candidate.notes.extend(metadata.notes or ["Repository availability could not be confirmed."])
        return

    candidate.availability_status = ArtifactStatus.FOUND
    corpus = " ".join(filter(None, [metadata.description, metadata.readme_excerpt]))
    title = analysis.paper.title or ""
    title_match = bool(title and corpus and token_set_ratio(title, corpus) >= 90.0)
    author_match = any(
        author.split()[-1].casefold() in corpus.casefold()
        for author in analysis.paper.authors
        if author.split()
    )
    explicit_official = bool(re.search(r"\b(official|our)\s+(?:code|implementation|repository)\b", candidate.context, re.IGNORECASE))
    ambiguous_wording = bool(re.search(r"\b(unofficial|possible|mirror|related repository)\b", candidate.context, re.IGNORECASE))
    if ambiguous_wording:
        candidate.relationship_status = ArtifactStatus.AMBIGUOUS
        candidate.confidence = ArtifactConfidence.LOW
        candidate.notes.append("The paper context does not establish an official relationship.")
    elif title_match and (author_match or explicit_official):
        candidate.relationship_status = ArtifactStatus.VERIFIED
        candidate.confidence = ArtifactConfidence.HIGH
        candidate.notes.append("Paper title and authors/official wording match repository text.")
    elif title_match or explicit_official:
        candidate.relationship_status = ArtifactStatus.VERIFIED
        candidate.confidence = ArtifactConfidence.HIGH
        candidate.notes.append("Direct paper link and repository text strongly establish identity.")
    else:
        candidate.relationship_status = ArtifactStatus.FOUND
        candidate.confidence = ArtifactConfidence.MEDIUM
        candidate.notes.append("Repository was explicitly linked, but its paper relationship is not fully verified.")
    if metadata.default_branch:
        candidate.version = metadata.default_branch
    if metadata.license_name:
        candidate.notes.append(f"Visible license: {metadata.license_name}.")


def _file_artifact_type(filename: str) -> ArtifactType | None:
    lower = filename.casefold()
    if lower in {"requirements.txt", "pyproject.toml", "setup.py", "environment.yml", "environment.yaml", "package.json", "package-lock.json", "poetry.lock"}:
        return ArtifactType.DEPENDENCY
    if lower in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
        return ArtifactType.CONTAINER
    if lower.endswith((".yaml", ".yml", ".toml", ".ini", ".cfg")) or "config" in lower:
        return ArtifactType.CONFIG
    if lower.endswith((".sh", ".bash")) or lower in {"train.py", "evaluate.py", "eval.py", "run.py"}:
        return ArtifactType.EXECUTION_SCRIPT
    if lower.endswith((".ckpt", ".pth", ".pt", ".safetensors")):
        return ArtifactType.CHECKPOINT
    return None


def _candidate_key(candidate: _Candidate) -> tuple[str, str]:
    if candidate.repository and candidate.type == ArtifactType.CODE:
        return candidate.type.value, candidate.repository.casefold()
    if candidate.source_url:
        return candidate.type.value, candidate.source_url.casefold()
    return candidate.type.value, f"{candidate.experiment_id}:{candidate.name}".casefold()


def discover_artifacts(
    paper_text: str,
    analysis: ResearchAnalysis,
    *,
    repository_provider: RepositoryMetadataProvider | None = None,
) -> list[Artifact]:
    """Discover explicit artifacts and safe metadata without downloading or executing code."""

    candidates: list[_Candidate] = []
    provider = repository_provider
    repository_metadata: dict[str, RepositoryMetadata] = {}

    for raw_url, start, end in _url_candidates(paper_text):
        try:
            normalized = normalize_public_url(raw_url)
        except ValueError:
            continue
        context = _context(paper_text, start, end)
        artifact_type = _classify_url(normalized, context)
        if artifact_type is None:
            continue
        repository = None
        source = urllib.parse.urlsplit(normalized).hostname
        try:
            repository = normalize_repository_url(normalized)
            normalized = repository
            source = parse_repository_url(repository)[0]
        except ValueError:
            pass
        name = repository.rsplit("/", 1)[-1] if repository else None
        if not name:
            parsed_url = urllib.parse.urlsplit(normalized)
            if parsed_url.path and parsed_url.path != "/":
                name = parsed_url.path.strip("/").split("/")[-1].replace("-", " ").replace("_", " ")
                if not name:
                    name = parsed_url.hostname
            else:
                name = parsed_url.hostname

        candidate = _Candidate(
            type=artifact_type,
            name=name,
            source_url=normalized,
            discovery_method=(
                ArtifactDiscoveryMethod.SUPPLEMENTARY_LINK
                if artifact_type == ArtifactType.SUPPLEMENTARY
                else ArtifactDiscoveryMethod.PAPER_URL
            ),
            context=context,
            evidence_location=_location_before(paper_text, start),
            experiment_id=_associate_experiment(context, analysis.experiments),
            repository=repository,
            source=source,
        )
        candidates.append(candidate)

    # Deduplicate before network access so repeated links cause one provider lookup.
    deduplicated: dict[tuple[str, str], _Candidate] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key not in deduplicated:
            deduplicated[key] = candidate
    candidates = list(deduplicated.values())

    for candidate in list(candidates):
        if candidate.type != ArtifactType.CODE or not candidate.repository:
            continue
        try:
            if provider is None:
                provider = PublicRepositoryMetadataProvider()
            metadata = repository_metadata.get(candidate.repository)
            if metadata is None:
                metadata = provider.inspect(candidate.repository)
                repository_metadata[candidate.repository] = metadata
            _repository_relationship(candidate, metadata, analysis)
        except Exception:
            candidate.availability_status = ArtifactStatus.INACCESSIBLE
            candidate.relationship_status = ArtifactStatus.PARTIAL
            candidate.confidence = ArtifactConfidence.LOW
            candidate.notes.append("Repository metadata inspection failed; no code was downloaded or executed.")
            continue

        if not metadata.accessible:
            continue
        for filename in metadata.visible_files:
            child_type = _file_artifact_type(filename)
            if child_type is None:
                continue
            branch = metadata.default_branch or "HEAD"
            child_url = f"{metadata.canonical_url}/blob/{urllib.parse.quote(branch)}/{urllib.parse.quote(filename)}"
            candidates.append(_Candidate(
                type=child_type,
                name=filename,
                source_url=child_url,
                discovery_method=ArtifactDiscoveryMethod.PUBLIC_REPOSITORY_LOOKUP,
                context=metadata.readme_excerpt or metadata.description or "",
                evidence_location=candidate.evidence_location,
                experiment_id=candidate.experiment_id,
                repository=metadata.canonical_url,
                source=metadata.platform,
                relationship_status=(
                    ArtifactStatus.VERIFIED
                    if candidate.relationship_status == ArtifactStatus.VERIFIED
                    else ArtifactStatus.PARTIAL
                ),
                availability_status=ArtifactStatus.FOUND,
                confidence=(
                    ArtifactConfidence.HIGH
                    if candidate.relationship_status == ArtifactStatus.VERIFIED
                    else ArtifactConfidence.MEDIUM
                ),
                description=f"Visible repository file: {filename}",
                version=metadata.default_branch,
                commit=metadata.latest_commit,
                notes=["File presence was inspected as metadata only; it was not downloaded or executed."],
            ))

    # Structured experiment fields establish an expected artifact, not a public version.
    for experiment in analysis.experiments:
        expectations = [
            (ArtifactType.DATASET, experiment.dataset, ArtifactDiscoveryMethod.DATASET_MENTION),
            (ArtifactType.MODEL, experiment.model, ArtifactDiscoveryMethod.MODEL_MENTION),
        ]
        for artifact_type, name, method in expectations:
            if not name:
                continue
            already_linked = any(
                item.type == artifact_type and item.experiment_id == experiment.id
                for item in candidates
            )
            if already_linked:
                continue
            candidates.append(_Candidate(
                type=artifact_type,
                name=name,
                source_url=None,
                identifier=name,
                discovery_method=method,
                context=experiment.objective,
                evidence_location=(experiment.evidence_locations[0] if experiment.evidence_locations else None),
                experiment_id=experiment.id,
                relationship_status=ArtifactStatus.PARTIAL,
                availability_status=ArtifactStatus.MISSING,
                confidence=ArtifactConfidence.HIGH,
                notes=["The experiment names this artifact, but no exact public URL/version was established."],
            ))

    lower_text = paper_text.casefold()
    missing_expectations = [
        (ArtifactType.CODE, r"\b(?:source )?code (?:is |will be )?available\b", "Code availability is mentioned without an identifiable public URL."),
        (ArtifactType.SUPPLEMENTARY, r"\b(?:supplementary|supplemental) material\b", "Supplementary material is mentioned without an identifiable public URL."),
    ]
    for artifact_type, pattern, note in missing_expectations:
        if re.search(pattern, lower_text) and not any(item.type == artifact_type for item in candidates):
            candidates.append(_Candidate(
                type=artifact_type,
                name=None,
                source_url=None,
                discovery_method=ArtifactDiscoveryMethod.PAPER_TEXT,
                context="",
                evidence_location=None,
                relationship_status=ArtifactStatus.PARTIAL,
                availability_status=ArtifactStatus.MISSING,
                confidence=ArtifactConfidence.MEDIUM,
                notes=[note],
            ))

    final_candidates: list[_Candidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key not in seen:
            final_candidates.append(candidate)
            seen.add(key)

    return [
        Artifact(
            artifact_id=f"ART-{index:03d}",
            experiment_id=item.experiment_id,
            type=item.type,
            name=item.name,
            source=item.source,
            source_url=item.source_url,
            identifier=item.identifier,
            repository=item.repository,
            version=item.version,
            commit=item.commit,
            discovery_method=item.discovery_method,
            evidence_location=item.evidence_location,
            description=item.description,
            relationship_status=item.relationship_status,
            availability_status=item.availability_status,
            confidence=item.confidence,
            notes=item.notes,
        )
        for index, item in enumerate(final_candidates, start=1)
    ]
