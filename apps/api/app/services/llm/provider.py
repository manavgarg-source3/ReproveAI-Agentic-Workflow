"""Provider-neutral contract for research analysis."""

from typing import Protocol

from app.schemas.research import ResearchAnalysis


class ResearchLLMProvider(Protocol):
    """A provider that maps extracted paper text to the stable research schema."""

    def analyze(self, text: str) -> ResearchAnalysis:
        """Analyze extracted research text without changing the API contract."""
        ...

    def close(self) -> None:
        """Release provider resources."""
        ...
