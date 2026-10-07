"""Deterministic claim-to-excerpt matching inside the uploaded paper."""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz.fuzz import token_set_ratio

from app.schemas.research import Claim
from app.services.scholarly.scientometric_adapter import _ensure_engine_path


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "with",
}


@dataclass(frozen=True, slots=True)
class PaperEvidenceMatch:
    excerpt: str
    location: str | None
    similarity: float
    claim_token_coverage: float


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("∆", " delta ").replace("δ", " delta ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _content_tokens(value: str) -> set[str]:
    return {
        token for token in _normalized(value).split()
        if len(token) > 1 and token not in _STOPWORDS
    }


class PaperEvidenceMapper:
    """Locate bounded paper excerpts that visibly report extracted claims."""

    def __init__(
        self,
        paper_text: str,
        *,
        minimum_similarity: float = 70.0,
        minimum_claim_coverage: float = 0.45,
    ) -> None:
        _ensure_engine_path()
        from src.parsing.section_segmenter import segment_manuscript

        body, _references, _metadata = segment_manuscript(paper_text)
        self.lines = [
            re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip()
            for line in body.splitlines()
            if len(line.strip()) > 3
        ]
        self.minimum_similarity = minimum_similarity
        self.minimum_claim_coverage = minimum_claim_coverage

    def find(self, claim: Claim) -> PaperEvidenceMatch | None:
        claim_tokens = _content_tokens(claim.claim_text)
        if not claim_tokens or not self.lines:
            return None

        best: tuple[float, float, int, str] | None = None
        # Six adjacent PDF lines are enough to retain table captions and
        # wrapped prose without returning whole pages as alleged evidence.
        for center in range(len(self.lines)):
            excerpt = " ".join(
                self.lines[max(0, center - 2): min(len(self.lines), center + 4)]
            )
            excerpt_tokens = _content_tokens(excerpt)
            coverage = len(claim_tokens & excerpt_tokens) / len(claim_tokens)
            similarity = float(token_set_ratio(_normalized(claim.claim_text), _normalized(excerpt)))
            rank = similarity + (coverage * 20.0)
            if best is None or rank > best[0]:
                best = (rank, similarity, center, excerpt)

        if best is None:
            return None
        _rank, similarity, _center, excerpt = best
        coverage = len(claim_tokens & _content_tokens(excerpt)) / len(claim_tokens)
        if similarity < self.minimum_similarity or coverage < self.minimum_claim_coverage:
            return None

        location = claim.evidence_locations[0] if claim.evidence_locations else None
        return PaperEvidenceMatch(
            excerpt=excerpt[:1_500].rstrip(),
            location=location,
            similarity=round(similarity / 100.0, 4),
            claim_token_coverage=round(coverage, 4),
        )
