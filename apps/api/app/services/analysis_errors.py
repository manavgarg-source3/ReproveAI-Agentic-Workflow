"""Safe domain errors raised by the research-analysis layer."""


class ResearchAnalysisError(RuntimeError):
    """Base class for controlled analysis failures."""


class AnalysisConfigurationError(ResearchAnalysisError):
    """Raised when required analyzer configuration is unavailable or invalid."""


class AnalysisInputTooLargeError(ResearchAnalysisError):
    """Raised when extracted text exceeds the configured provider input limit."""


class AnalysisTimeoutError(ResearchAnalysisError):
    """Raised when the provider does not respond within the configured timeout."""


class AnalysisRateLimitError(ResearchAnalysisError):
    """Raised when the provider rejects a request because of quota or rate limits."""


class AnalysisProviderError(ResearchAnalysisError):
    """Raised when the provider cannot complete an analysis request."""


class AnalysisResponseError(ResearchAnalysisError):
    """Raised when provider output is empty, malformed, or fails validation."""

