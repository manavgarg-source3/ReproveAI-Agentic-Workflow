"""Tests for the provider-neutral analyzer boundary."""

from app.schemas.research import PaperMetadata, ResearchAnalysis
from app.services.analyzer import analyze_research_text


class StubProvider:
    closed = False

    def analyze(self, text: str) -> ResearchAnalysis:
        assert "paper" in text
        return ResearchAnalysis(paper=PaperMetadata(title="Stub Paper"))

    def close(self) -> None:
        self.closed = True


def test_analyzer_uses_injected_provider() -> None:
    result = analyze_research_text("paper", provider=StubProvider())

    assert result.paper.title == "Stub Paper"
