"""
Unified LLM client — the single interface all downstream phases use.

Every phase that needs an LLM call (extraction, summarisation, risk
explanation) imports and calls functions from this module. They never
call provider.complete() or groq directly.

Public API:
  complete_text(prompt, ...) → str
  complete_json(prompt, required_keys, ...) → dict
  complete_with_schema(prompt, schema_class, ...) → Pydantic model instance

All calls:
  - Apply output guardrails.
  - Add AI disclaimer to text responses.
  - Log token usage for cost tracking.
  - Return only the content — callers never see LLMResponse directly.
"""
from __future__ import annotations

import json
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.guardrails import (
    GuardrailResult,
    add_ai_disclaimer,
    check_output,
    validate_json_output,
)
from app.ai.prompt_builder import SYSTEM_PROMPT
from app.ai.provider import LLMMessage, LLMRequest, LLMResponse, get_llm_provider
from app.core.config import get_settings
from app.core.exceptions import LLMError, LLMResponseValidationError
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


async def complete_text(
    prompt: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    add_disclaimer: bool = True,
) -> str:
    """
    Send a prompt and return a plain-text response.

    Args:
        prompt:          The user prompt (system prompt is added automatically).
        temperature:     Override default extraction temperature.
        max_tokens:      Override default max tokens.
        model:           Override default model.
        add_disclaimer:  Prepend AI disclaimer to the response.

    Returns:
        Guardrailed, possibly-disclaimed response string.

    Raises:
        LLMError: Provider not configured or request failed.
    """
    settings = get_settings()
    provider = get_llm_provider()

    if not provider.is_configured():
        raise LLMError("LLM provider not configured. Set GROQ_API_KEY in .env.")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content=prompt)],
        system_prompt=SYSTEM_PROMPT,
        temperature=temperature or settings.llm_temperature_summarization,
        max_tokens=max_tokens or settings.llm_max_tokens,
        model=model,
        json_mode=False,
    )

    async with StageLogger(stage=ProcessingStage.LLM_CALL):
        response: LLMResponse = await provider.complete(request)

    # Output guardrails
    guard = check_output(response.content, expected_type="text")
    if not guard.passed:
        raise LLMError(
            f"LLM output failed guardrail checks: {'; '.join(guard.violations)}"
        )

    content = guard.content
    if add_disclaimer:
        content = add_ai_disclaimer(content)

    if guard.warnings:
        for w in guard.warnings:
            logger.warning("LLM output guardrail warning", warning=w)

    return content


async def complete_json(
    prompt: str,
    required_keys: list[str] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> dict:
    """
    Send a prompt and parse the response as a JSON object.

    The model is instructed to return JSON (response_format=json_object).

    Returns:
        Parsed dict.

    Raises:
        LLMResponseValidationError: Response is not valid JSON or missing keys.
        LLMError:                   Provider error.
    """
    settings = get_settings()
    provider = get_llm_provider()

    if not provider.is_configured():
        raise LLMError("LLM provider not configured. Set GROQ_API_KEY in .env.")

    request = LLMRequest(
        messages=[LLMMessage(role="user", content=prompt)],
        system_prompt=SYSTEM_PROMPT,
        temperature=temperature or settings.llm_temperature_extraction,
        max_tokens=max_tokens or settings.llm_max_tokens,
        model=model,
        json_mode=True,
    )

    async with StageLogger(stage=ProcessingStage.LLM_CALL):
        response: LLMResponse = await provider.complete(request)

    # Output guardrails
    guard = check_output(response.content, expected_type="json")
    if not guard.passed:
        raise LLMError(
            f"LLM JSON output failed guardrail checks: {'; '.join(guard.violations)}"
        )

    return validate_json_output(guard.content, required_keys=required_keys)


async def complete_with_schema(
    prompt: str,
    schema_class: Type[T],
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> T:
    """
    Send a prompt and parse the response into a Pydantic model instance.

    The prompt should include the JSON schema so the model knows what to return.

    Returns:
        Validated Pydantic model instance.

    Raises:
        LLMResponseValidationError: Response doesn't match the schema.
        LLMError:                   Provider error.
    """
    # Build schema hint to append to prompt
    schema_hint = (
        f"\n\nRespond with ONLY a valid JSON object matching this schema:\n"
        f"{json.dumps(schema_class.model_json_schema(), indent=2)}"
    )
    full_prompt = prompt + schema_hint

    parsed_dict = await complete_json(
        prompt=full_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )

    try:
        return schema_class.model_validate(parsed_dict)
    except ValidationError as exc:
        raise LLMResponseValidationError(
            f"LLM response does not match schema {schema_class.__name__}: {exc}"
        ) from exc


def llm_is_available() -> bool:
    """Return True if the LLM provider is configured and reachable."""
    return get_llm_provider().is_configured()


def token_estimate(text: str) -> int:
    """
    Rough token count estimate without calling the tokenizer.
    1 token ≈ 4 characters for English text.
    Use tiktoken for precision when needed.
    """
    return max(1, len(text) // 4)


async def count_tokens_precise(text: str, model: str | None = None) -> int:
    """
    Precise token count using tiktoken (if available).
    Falls back to character estimate if tiktoken is not installed.
    """
    settings = get_settings()
    target_model = model or settings.llm_model
    try:
        import tiktoken  # type: ignore[import]
        # gpt-oss models use cl100k_base encoding
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except (ImportError, Exception):
        return token_estimate(text)
