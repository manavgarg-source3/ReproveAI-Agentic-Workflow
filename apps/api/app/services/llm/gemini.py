"""Google Gemini implementation of the research-analysis provider."""

import json
import logging
import os
import re
import time
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
DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_CHARACTERS = 45_000
DEFAULT_TIMEOUT_SECONDS = 120.0

# Application-level retry for transient connection errors (TCP resets,
# server disconnects) that the SDK's HTTP-status-based retry cannot catch.
CONNECTION_RETRY_ATTEMPTS = 3
CONNECTION_RETRY_BACKOFF_BASE = 2.0  # seconds; doubles each attempt


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


def _is_connection_error(exc: Exception) -> bool:
    """Return *True* for transient connection-level failures worth retrying.

    The Google Gen AI SDK wraps low-level transport failures (TCP resets,
    server disconnects) in ``APIConnectionError``.  We match by class name
    so we don't need a hard import of the private exception hierarchy.
    """
    name = type(exc).__name__
    if name in {"APIConnectionError", "ConnectionError"}:
        return True
    status_code = getattr(exc, "status_code", getattr(exc, "code", None))
    if status_code is None:
        # No HTTP status → transport-level failure
        msg = str(exc).lower()
        return "disconnect" in msg or "connection" in msg or "reset" in msg
    return False


# Regex to strip ```json ... ``` or ``` ... ``` fenced blocks.
_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)


def _extract_json(text: str) -> Any:
    """Parse JSON from model output, tolerating markdown fences and prose.

    Many models (especially older or fallback ones) wrap their JSON in
    ````` ```json ... ``` ````` blocks or add explanatory text before/after
    the payload.  This function tries increasingly aggressive extraction
    strategies before giving up.
    """
    # Strip BOM and surrounding whitespace.
    cleaned = text.strip().lstrip("\ufeff")

    # 1. Direct parse — works when the model is well-behaved.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Extract from markdown code fences.
    fence_match = _FENCED_JSON_RE.search(cleaned)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find the first top-level { … } by bracket-matching.
    start = cleaned.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # Nothing worked — raise so the caller can log and surface the error.
    raise ValueError("Could not extract valid JSON from model output")


def _coerce_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Pre-process the model's JSON output to tolerate common deviations.

    Older or fallback models may:
    - Add extra keys that StrictModel (extra='forbid') rejects
    - Use string representations for numeric fields
    - Omit required sub-objects

    This function sanitises the payload so Pydantic validation succeeds.
    """

    # Known top-level keys for ResearchAnalysis
    _TOP_KEYS = {"paper", "claims", "experiments", "methods", "references"}
    _PAPER_KEYS = {"title", "authors", "year", "abstract"}
    _CLAIM_KEYS = {"id", "claim_text", "claim_type", "metric", "reported_value", "evidence_locations"}
    _EXPERIMENT_KEYS = {"id", "objective", "dataset", "split", "model", "metric", "baseline", "reported_result", "evidence_locations"}
    _REFERENCE_KEYS = {"id", "citation_text", "title", "authors", "year", "doi"}

    def _strip_extra(obj: dict, allowed: set[str]) -> dict:
        return {k: v for k, v in obj.items() if k in allowed}

    def _to_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _to_optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # Ensure top-level structure
    result = _strip_extra(raw, _TOP_KEYS)

    # Paper metadata
    paper = result.get("paper")
    if not isinstance(paper, dict):
        paper = {}
    paper = _strip_extra(paper, _PAPER_KEYS)
    paper["year"] = _to_optional_int(paper.get("year"))
    if not isinstance(paper.get("authors"), list):
        paper["authors"] = []
    result["paper"] = paper

    # Claims
    claims = result.get("claims")
    if not isinstance(claims, list):
        claims = []
    coerced_claims = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        claim = _strip_extra(claim, _CLAIM_KEYS)
        claim.setdefault("id", f"claim_{i + 1}")
        claim.setdefault("claim_text", "")
        claim.setdefault("claim_type", "unspecified")
        claim["reported_value"] = _to_optional_float(claim.get("reported_value"))
        if not isinstance(claim.get("evidence_locations"), list):
            claim["evidence_locations"] = []
        coerced_claims.append(claim)
    result["claims"] = coerced_claims

    # Experiments
    experiments = result.get("experiments")
    if not isinstance(experiments, list):
        experiments = []
    coerced_experiments = []
    for i, exp in enumerate(experiments):
        if not isinstance(exp, dict):
            continue
        exp = _strip_extra(exp, _EXPERIMENT_KEYS)
        exp.setdefault("id", f"experiment_{i + 1}")
        exp.setdefault("objective", "")
        exp["reported_result"] = _to_optional_float(exp.get("reported_result"))
        if not isinstance(exp.get("evidence_locations"), list):
            exp["evidence_locations"] = []
        coerced_experiments.append(exp)
    result["experiments"] = coerced_experiments

    # Methods
    methods = result.get("methods")
    if not isinstance(methods, list):
        methods = []
    result["methods"] = [str(m) for m in methods if m]

    # References
    references = result.get("references")
    if not isinstance(references, list):
        references = []
    coerced_refs = []
    for i, ref in enumerate(references):
        if not isinstance(ref, dict):
            continue
        ref = _strip_extra(ref, _REFERENCE_KEYS)
        ref.setdefault("id", f"ref_{i + 1}")
        ref.setdefault("citation_text", "")
        ref["year"] = _to_optional_int(ref.get("year"))
        if not isinstance(ref.get("authors"), list):
            ref["authors"] = []
        coerced_refs.append(ref)
    result["references"] = coerced_refs

    return result


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


class _ModelUnavailableError(Exception):
    """Raised internally when a specific model returns 503 UNAVAILABLE."""


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
        self.fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip()
        if self.fallback_model == self.model:
            self.fallback_model = ""  # no point falling back to the same model

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
            http_options=types.HttpOptions(
                timeout=int(self.timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=3,
                    # A 503 means the selected model is temporarily unavailable.
                    # Let ``analyze`` switch models immediately instead of making
                    # several slow SDK retries before trying the configured fallback.
                    http_status_codes=[408, 500, 502, 504],
                ),
            ),
        )

    def close(self) -> None:
        """Release the SDK HTTP client owned by this provider instance."""

        self._client.close()

    def _call_with_retries(self, model: str, text: str) -> Any:
        """Call the API with connection-level retries.

        Raises ``_ModelUnavailableError`` on 503 so the caller can try
        a fallback model.  Other errors propagate immediately.
        """
        last_exc: Exception | None = None
        for attempt in range(1, CONNECTION_RETRY_ATTEMPTS + 1):
            try:
                return self._client.interactions.create(
                    model=model,
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
                status = getattr(exc, "status_code", getattr(exc, "code", None))
                if status == 503:
                    raise _ModelUnavailableError(
                        f"Model {model} returned 503 UNAVAILABLE"
                    ) from exc
                if _is_connection_error(exc) and attempt < CONNECTION_RETRY_ATTEMPTS:
                    wait = CONNECTION_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini connection error on attempt %d/%d (%s), retrying in %.1fs: %s",
                        attempt, CONNECTION_RETRY_ATTEMPTS, model, wait, exc,
                    )
                    last_exc = exc
                    time.sleep(wait)
                    continue
                _raise_provider_error(exc)
            except (httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                if attempt < CONNECTION_RETRY_ATTEMPTS:
                    wait = CONNECTION_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini connection error on attempt %d/%d (%s), retrying in %.1fs: %s",
                        attempt, CONNECTION_RETRY_ATTEMPTS, model, wait, exc,
                    )
                    last_exc = exc
                    time.sleep(wait)
                    continue
                _raise_provider_error(exc)
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise AnalysisTimeoutError(
                    "The research analyzer timed out. Try again later."
                ) from exc
            except Exception as exc:
                if getattr(exc, "status_code", None) is not None:
                    # Could also be a 503 from a non-standard exception wrapper
                    if getattr(exc, "status_code", None) == 503:
                        raise _ModelUnavailableError(
                            f"Model {model} returned 503 UNAVAILABLE"
                        ) from exc
                    _raise_provider_error(exc)
                logger.exception("Unexpected Gemini provider failure")
                _raise_provider_error(exc)
        # All connection retries exhausted
        _raise_provider_error(last_exc or RuntimeError("All connection retries exhausted"))

    def analyze(self, text: str) -> ResearchAnalysis:
        if len(text) > self.max_characters:
            raise AnalysisInputTooLargeError(
                f"Extracted paper text has {len(text):,} characters; the configured "
                f"analysis limit is {self.max_characters:,}."
            )

        models_to_try = [self.model]
        if self.fallback_model:
            models_to_try.append(self.fallback_model)

        last_exc: Exception | None = None
        for model in models_to_try:
            try:
                interaction = self._call_with_retries(model, text)
                break  # success
            except _ModelUnavailableError as exc:
                logger.warning(
                    "Model %s unavailable (503), trying next fallback…", model,
                )
                last_exc = exc.__cause__ or exc
                continue
        else:
            _raise_provider_error(last_exc or RuntimeError("All models unavailable"))

        output = getattr(interaction, "output_text", None)
        if not isinstance(output, str) or not output.strip():
            raise AnalysisResponseError("The research analyzer returned an empty response.")

        try:
            payload = _extract_json(output)
        except (json.JSONDecodeError, ValueError) as exc:
            # Log the first 500 chars so we can diagnose the wrapping pattern
            logger.warning(
                "Gemini returned malformed JSON (first 500 chars): %.500s", output,
            )
            raise AnalysisResponseError(
                "The research analyzer returned malformed structured output."
            ) from exc

        if not isinstance(payload, dict):
            logger.warning("Gemini returned non-object JSON: %s", type(payload).__name__)
            raise AnalysisResponseError(
                "The research analyzer returned malformed structured output."
            )

        # Coerce the payload to match the schema before strict validation.
        original_keys = set(payload.keys())
        payload = _coerce_payload(payload)
        stripped = original_keys - set(payload.keys())
        if stripped:
            logger.info("Stripped extra top-level keys from Gemini output: %s", stripped)

        try:
            return ResearchAnalysis.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Gemini response failed schema validation: %s", exc)
            raise AnalysisResponseError(
                "The research analyzer response failed schema validation."
            ) from exc
