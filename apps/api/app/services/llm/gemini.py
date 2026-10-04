"""Google Gemini implementation of the research-analysis provider."""

import json
import logging
import os
from copy import deepcopy
from typing import Any, NoReturn

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.schemas.research import ResearchAnalysis
from app.services.analysis_errors import (
    AnalysisConfigurationError,
    AnalysisInputTooLargeError,
    AnalysisProviderError,
    AnalysisRateLimitError,
    AnalysisResponseError,
    AnalysisTimeoutError,
)
from app.services.research_prompt import (
    RESEARCH_ANALYZER_SYSTEM_PROMPT,
    build_research_analysis_input,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_MAX_CHARACTERS = 45_000
DEFAULT_TIMEOUT_SECONDS = 120.0


def _positive_number(raw_value: str | None, default: float, variable: str) -> float:
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise AnalysisConfigurationError(f"{variable} must be a positive number.") from exc
    if value <= 0:
        raise AnalysisConfigurationError(f"{variable} must be a positive number.")
    return value


def _raise_provider_error(exc: Exception) -> NoReturn:
    """Translate SDK-version-specific failures without exposing provider details."""

    status_code = getattr(exc, "status_code", getattr(exc, "code", None))
    logger.warning(
        "Gemini API failure (type=%s, status=%s)",
        type(exc).__name__,
        status_code,
    )
    if status_code == 429:
        raise AnalysisRateLimitError(
            "The research analyzer is temporarily rate-limited. Try again later."
        ) from exc
    if status_code in {408, 504} or type(exc).__name__ == "APITimeoutError":
        raise AnalysisTimeoutError(
            "The research analyzer timed out. Try again later."
        ) from exc
    raise AnalysisProviderError(
        "The research analyzer provider could not complete the request."
    ) from exc


def _complete_response_schema() -> dict[str, Any]:
    """Require every response key while preserving nullable field types."""

    schema = deepcopy(ResearchAnalysis.model_json_schema())

    def require_properties(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
            for value in node.values():
                require_properties(value)
        elif isinstance(node, list):
            for value in node:
                require_properties(value)

    require_properties(schema)
    return schema


class GeminiResearchProvider:
    """Extract a strict ResearchAnalysis with Google's current Gen AI SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_characters: int | None = None,
        timeout_seconds: float | None = None,
        client: Any | None = None,
    ) -> None:
        resolved_api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        if not resolved_api_key and client is None:
            raise AnalysisConfigurationError(
                "Gemini analysis is not configured. Set GEMINI_API_KEY."
            )

        self.model = (model if model is not None else os.getenv("GEMINI_MODEL", DEFAULT_MODEL)).strip()
        if not self.model:
            raise AnalysisConfigurationError("GEMINI_MODEL must not be empty.")

        configured_limit = max_characters
        if configured_limit is None:
            configured_limit = int(
                _positive_number(
                    os.getenv("GEMINI_MAX_INPUT_CHARS"),
                    DEFAULT_MAX_CHARACTERS,
                    "GEMINI_MAX_INPUT_CHARS",
                )
            )
        if configured_limit <= 0:
            raise AnalysisConfigurationError("MAX_ANALYSIS_CHARACTERS must be positive.")
        self.max_characters = configured_limit

        self.timeout_seconds = timeout_seconds or _positive_number(
            os.getenv("GEMINI_TIMEOUT_SECONDS"),
            DEFAULT_TIMEOUT_SECONDS,
            "GEMINI_TIMEOUT_SECONDS",
        )
        if self.timeout_seconds <= 0:
            raise AnalysisConfigurationError("GEMINI_TIMEOUT_SECONDS must be positive.")

        self._client = client or genai.Client(
            api_key=resolved_api_key,
            http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
        )

    def close(self) -> None:
        """Release the SDK HTTP client owned by this provider instance."""

        self._client.close()

    def analyze(self, text: str) -> ResearchAnalysis:
        if len(text) > self.max_characters:
            raise AnalysisInputTooLargeError(
                f"Extracted paper text has {len(text):,} characters; the configured "
                f"analysis limit is {self.max_characters:,}."
            )

        try:
            interaction = self._client.interactions.create(
                model=self.model,
                input=build_research_analysis_input(text),
                system_instruction=RESEARCH_ANALYZER_SYSTEM_PROMPT,
                response_format=[
                    {
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": _complete_response_schema(),
                    }
                ],
                timeout=self.timeout_seconds,
            )
        except errors.APIError as exc:
            _raise_provider_error(exc)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise AnalysisTimeoutError(
                "The research analyzer timed out. Try again later."
            ) from exc
        except Exception as exc:
            if getattr(exc, "status_code", None) is not None:
                _raise_provider_error(exc)
            logger.exception("Unexpected Gemini provider failure")
            _raise_provider_error(exc)

        output = getattr(interaction, "output_text", None)
        if not isinstance(output, str) or not output.strip():
            raise AnalysisResponseError("The research analyzer returned an empty response.")

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.warning("Gemini returned malformed JSON: %s", exc)
            raise AnalysisResponseError(
                "The research analyzer returned malformed structured output."
            ) from exc

        try:
            return ResearchAnalysis.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Gemini response failed schema validation: %s", exc)
            raise AnalysisResponseError(
                "The research analyzer response failed schema validation."
            ) from exc
