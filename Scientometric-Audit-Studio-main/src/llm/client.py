"""
Universal LLM Client for Bibliometric Intelligence.
Supports local Ollama, OpenAI, Google Gemini, Groq, and OpenAI-compatible endpoints.
"""
import os
import json
import logging
import re
from typing import Dict, Any, Optional, List
import openai
from openai import OpenAI
import httpx

from config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_BASE_URL,
    LLM_API_KEY,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    GROQ_API_KEY,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified client providing resilient LLM chat completions with JSON schema extraction.
    """

    _instance: Optional["LLMClient"] = None

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.provider = (provider or LLM_PROVIDER or "ollama").lower()
        self.model = model or LLM_MODEL or "llama3:latest"
        self.timeout = timeout

        # Resolve provider-specific endpoints and keys
        if self.provider == "gemini":
            self.base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
            self.api_key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
            if not model:
                self.model = "gemini-1.5-flash"
        elif self.provider == "openai":
            self.base_url = base_url or "https://api.openai.com/v1"
            self.api_key = api_key or OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
            if not model:
                self.model = "gpt-4o-mini"
        elif self.provider == "groq":
            self.base_url = base_url or "https://api.groq.com/openai/v1"
            self.api_key = api_key or GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
            if not model:
                self.model = "llama-3.1-8b-instant"
        else:
            # Default to Ollama / local OpenAI-compatible endpoint
            self.provider = "ollama"
            self.base_url = base_url or LLM_BASE_URL or "http://localhost:11434/v1"
            self.api_key = api_key or LLM_API_KEY or "ollama"
            if not model:
                self.model = "llama3:latest"

        self._client: Optional[OpenAI] = None
        self._init_client()

    def _init_client(self):
        """Initializes the underlying OpenAI SDK client."""
        try:
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "placeholder",
                timeout=self.timeout,
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client for {self.provider}: {e}")
            self._client = None

    @classmethod
    def get_default(cls) -> "LLMClient":
        """Returns singleton default client instance."""
        if cls._instance is None:
            cls._instance = LLMClient()
        return cls._instance

    @property
    def available(self) -> bool:
        """Property wrapper around is_available()."""
        return self.is_available()

    def is_available(self) -> bool:
        """Probes whether the configured LLM provider is reachable."""
        try:
            if self.provider == "ollama":
                # Quick health check on Ollama tags endpoint
                probe_url = self.base_url.replace("/v1", "/api/tags").rstrip("/")
                r = httpx.get(probe_url, timeout=2.0)
                return r.status_code == 200
            elif self.provider in ("openai", "gemini", "groq"):
                return bool(self.api_key and len(self.api_key) > 5)
            return True
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Returns structured metadata about active provider and availability."""
        available = self.is_available()
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "available": available,
            "has_api_key": bool(self.api_key and self.api_key != "ollama"),
        }

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1500,
        json_mode: bool = True,
    ) -> Optional[str]:
        """
        Executes chat completion with JSON schema reinforcement.
        """
        if not self._client:
            self._init_client()
        if not self._client:
            return None

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            # Most modern endpoints accept response_format json_object
            try:
                kwargs["response_format"] = {"type": "json_object"}
            except Exception:
                pass

        try:
            resp = self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            # Fallback without json_object constraint if model doesn't support it
            if json_mode and "response_format" in kwargs:
                del kwargs["response_format"]
                try:
                    resp = self._client.chat.completions.create(**kwargs)
                    return resp.choices[0].message.content
                except Exception as inner_e:
                    logger.warning(f"LLM completion error without json_format: {inner_e}")
                    return None
            logger.warning(f"LLM completion error ({self.provider}/{self.model}): {e}")
            return None

    @staticmethod
    def extract_json(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Robust JSON extractor handling markdown fences, trailing text, or raw json.
        """
        if not raw_text or not raw_text.strip():
            return None

        text = raw_text.strip()

        # Check for ```json ... ``` codeblock
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if m:
            text = m.group(1).strip()

        # Find first '{' and last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass

        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            return None

