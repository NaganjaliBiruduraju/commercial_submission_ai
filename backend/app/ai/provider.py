"""
LLM provider abstraction layer.

Architecture:
  LLMProvider (abstract base)
      └── GroqProvider (concrete — uses groq async client)

Why an abstraction?
  The steering file specifies "Groq API (provider abstraction — swappable)".
  Wrapping the Groq client behind LLMProvider means:
    - Downstream code (extraction, summarisation, risk) calls provider.complete()
      and never imports groq directly.
    - Swapping to OpenAI, Anthropic, or a local Ollama server requires
      only a new provider class, not changes to callers.
    - Unit tests can inject a MockProvider that returns canned responses.

GroqProvider features:
  - Exponential back-off retry for rate-limit (429) and transient errors (5xx).
  - Hard timeout enforced via asyncio.wait_for (not just the Groq client timeout).
  - Request/response logging with redacted API key.
  - Token usage tracking (prompt + completion tokens from response).
  - Structured JSON output mode (response_format=json_object) when requested.
  - Configurable: model, temperature, max_tokens all overridable per-call.
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.exceptions import (
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

@dataclass
class LLMMessage:
    """A single message in the conversation."""
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """Unified response object returned by every provider."""
    content: str                    # raw text content
    model: str                      # model name that produced this response
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"     # "stop" | "length" | "content_filter"
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def was_truncated(self) -> bool:
        return self.finish_reason == "length"


@dataclass
class LLMRequest:
    """Parameters for a single LLM call."""
    messages: list[LLMMessage]
    model: str | None = None         # None → use provider default
    temperature: float | None = None  # None → use provider default
    max_tokens: int | None = None     # None → use provider default
    json_mode: bool = False           # request JSON object output
    system_prompt: str | None = None  # convenience: prepended as system message


# --------------------------------------------------------------------------- #
# Abstract base
# --------------------------------------------------------------------------- #

class LLMProvider(ABC):
    """
    Abstract LLM provider interface.

    All concrete providers must implement complete().
    """

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Send messages to the LLM and return a response.

        Raises:
            LLMTimeoutError:   Request exceeded timeout.
            LLMRateLimitError: Provider rate limit hit (after retries).
            LLMError:          Any other provider error.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the provider has valid credentials."""
        ...

    @abstractmethod
    def default_model(self) -> str:
        """Return the default model name for this provider."""
        ...


# --------------------------------------------------------------------------- #
# Groq implementation
# --------------------------------------------------------------------------- #

def _is_retriable(exc: BaseException) -> bool:
    """Return True for errors that should trigger a retry."""
    if isinstance(exc, LLMRateLimitError):
        return True
    if isinstance(exc, LLMError):
        msg = str(exc).lower()
        return any(kw in msg for kw in ("503", "502", "500", "server error", "overloaded"))
    return False


class GroqProvider(LLMProvider):
    """
    Groq API provider.

    Uses the official `groq` Python package (async client).
    Implements exponential back-off retry via tenacity.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_configured(self) -> bool:
        return bool(
            self._settings.groq_api_key
            and self._settings.groq_api_key != "your_groq_api_key_here"
        )

    def default_model(self) -> str:
        return self._settings.llm_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Call Groq and return a LLMResponse.

        Retries up to llm_max_retries times with exponential back-off
        for rate-limit and transient server errors.
        """
        if not self.is_configured():
            raise LLMError(
                "GROQ_API_KEY is not configured. "
                "Set it in .env to enable LLM features."
            )

        settings = self._settings
        model = request.model or settings.llm_model
        temperature = request.temperature if request.temperature is not None else settings.llm_temperature_extraction
        max_tokens = request.max_tokens or settings.llm_max_tokens
        timeout_s = settings.llm_timeout_seconds

        # Build message list
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Extra kwargs for structured output
        extra_kwargs: dict[str, Any] = {}
        if request.json_mode:
            extra_kwargs["response_format"] = {"type": "json_object"}

        last_exc: Exception | None = None
        start_time = time.monotonic()

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retriable),
                stop=stop_after_attempt(settings.llm_max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            ):
                with attempt:
                    try:
                        response = await asyncio.wait_for(
                            self._call_groq(
                                messages=messages,
                                model=model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                extra_kwargs=extra_kwargs,
                            ),
                            timeout=timeout_s,
                        )
                    except asyncio.TimeoutError as exc:
                        raise LLMTimeoutError(timeout_s) from exc

        except LLMTimeoutError:
            raise
        except LLMRateLimitError:
            raise
        except Exception as exc:
            raise LLMError(f"Groq request failed after retries: {exc}") from exc

        latency_ms = (time.monotonic() - start_time) * 1000

        usage = response.usage
        llm_response = LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            total_tokens=getattr(usage, "total_tokens", 0),
            finish_reason=response.choices[0].finish_reason or "stop",
            latency_ms=round(latency_ms, 1),
        )

        logger.info(
            "LLM call complete",
            model=llm_response.model,
            prompt_tokens=llm_response.prompt_tokens,
            completion_tokens=llm_response.completion_tokens,
            latency_ms=llm_response.latency_ms,
            finish_reason=llm_response.finish_reason,
        )

        if llm_response.was_truncated:
            logger.warning(
                "LLM response was truncated (finish_reason=length)",
                model=model,
                max_tokens=max_tokens,
            )

        return llm_response

    async def _call_groq(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        extra_kwargs: dict,
    ) -> Any:
        """Raw Groq API call — separated so retry wraps the whole call."""
        try:
            import groq as groq_lib  # type: ignore[import]
        except ImportError:
            raise LLMError("groq package not installed. Run: pip install groq")

        try:
            client = groq_lib.AsyncGroq(api_key=self._settings.groq_api_key)
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **extra_kwargs,
            )
            return response
        except Exception as exc:
            exc_str = str(exc).lower()
            if "rate limit" in exc_str or "429" in exc_str:
                raise LLMRateLimitError() from exc
            raise LLMError(str(exc)) from exc


# --------------------------------------------------------------------------- #
# Singleton accessor
# --------------------------------------------------------------------------- #

_default_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """
    Return the application-level LLM provider singleton.

    Call this instead of constructing GroqProvider directly so tests
    can substitute a mock via set_llm_provider().
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = GroqProvider()
    return _default_provider


def set_llm_provider(provider: LLMProvider) -> None:
    """Override the default provider (for testing)."""
    global _default_provider
    _default_provider = provider
