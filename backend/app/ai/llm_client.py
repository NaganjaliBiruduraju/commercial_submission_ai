"""
Unified LLM client — the single interface all downstream phases use.

Public API:
  complete_freeform(prompt, ...)           → str   ← NEW primary function
      The LLM returns exactly what the prompt asks for.
      No schema enforced. Output shape is 100% driven by your prompt.
      Use this for extraction, summarisation, analysis — anything.

  complete_text(prompt, ...)               → str   (text + AI disclaimer)
  complete_json(prompt, required_keys, ...) → dict (JSON mode, optional key check)
  complete_with_schema(prompt, schema, ...) → Pydantic model

Design principle (updated):
  The prompt is the contract. Whatever structure you describe in the prompt
  is what the LLM produces. The client's job is:
    1. Apply input safety checks (injection, PII scrub, token budget).
    2. Call the provider.
    3. Apply output safety checks (forbidden patterns, length cap).
    4. Return the raw content — no further reshaping.
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


async def complete_freeform(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    document_id: str | None = None,
    apply_pii_scrub: bool = True,
    add_disclaimer: bool = False,
) -> str:
    """
    Send a prompt and return the LLM response exactly as shaped by the prompt.

    This is the PRIMARY extraction/analysis function.
    The output structure is 100% defined by whatever your prompt says.
    No JSON schema is enforced. No fixed field list is required.

    The prompt is the contract:
      - Ask for a paragraph → get a paragraph.
      - Ask for a markdown table → get a markdown table.
      - Ask for JSON with your own keys → get that JSON.
      - Ask for a list of risk factors → get a list.

    Safety checks still run:
      - Input:  injection detection, PII scrub, token budget enforcement.
      - Output: forbidden credential/decision patterns, length cap.

    Args:
        prompt:          Your complete prompt including any output format instructions.
        system_prompt:   Override the default system prompt (use sparingly).
        temperature:     Defaults to extraction temperature (0.1).
        max_tokens:      Defaults to settings.llm_max_tokens.
        model:           Override model name.
        document_id:     For injection check logging context.
        apply_pii_scrub: Set False if you know the prompt has no PII.
        add_disclaimer:  Prepend AI-generated disclaimer to the response.

    Returns:
        Raw LLM response string — shaped exactly as your prompt requested.

    Raises:
        LLMError:                  Provider not configured or call failed.
        PromptInjectionDetectedError: Injection pattern found in prompt.
    """
    settings = get_settings()
    provider = get_llm_provider()

    if not provider.is_configured():
        raise LLMError("LLM provider not configured. Set GROQ_API_KEY in .env.")

    # Input guardrails on the prompt itself
    if apply_pii_scrub:
        from app.ai.guardrails import sanitise_input
        prompt, _ = sanitise_input(
            prompt,
            max_tokens=max_tokens or settings.llm_max_tokens,
            document_id=document_id,
        )

    sys = system_prompt or SYSTEM_PROMPT

    request = LLMRequest(
        messages=[LLMMessage(role="user", content=prompt)],
        system_prompt=sys,
        temperature=temperature if temperature is not None else settings.llm_temperature_extraction,
        max_tokens=max_tokens or settings.llm_max_tokens,
        model=model,
        json_mode=False,  # let the prompt control the output format
    )

    async with StageLogger(stage=ProcessingStage.LLM_CALL):
        response: LLMResponse = await provider.complete(request)

    # Output guardrails — check for forbidden patterns, length cap
    guard = check_output(response.content, expected_type="text")
    if not guard.passed:
        raise LLMError(
            f"LLM output failed safety checks: {'; '.join(guard.violations)}"
        )

    content = guard.content

    if add_disclaimer:
        content = add_ai_disclaimer(content)

    if guard.warnings:
        for w in guard.warnings:
            logger.warning("LLM output warning", warning=w)

    logger.info(
        "complete_freeform done",
        chars_out=len(content),
        finish_reason=response.finish_reason,
        tokens=response.total_tokens,
    )

    return content


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
