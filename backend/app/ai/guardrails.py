"""
LLM input and output guardrails.

Per the steering file (03-llm-boundaries-and-guardrails.md):

INPUT guardrails (before text reaches the LLM):
  1. Prompt injection detection — raise PromptInjectionDetectedError if
     document text contains known injection patterns.
  2. PII scrubbing — replace SSNs, credit cards, phone numbers with
     [REDACTED] placeholders before the text enters the prompt.
     NOTE: we do NOT remove all PII (insurance documents legitimately
     contain names, addresses, policy numbers). We only redact the
     highest-risk patterns that serve no insurance underwriting purpose.
  3. Context length enforcement — truncate text to fit within the
     token budget, preserving the beginning and end of the document.

OUTPUT guardrails (after the LLM responds):
  1. JSON schema validation — verify the response matches the expected
     Pydantic schema before returning it to callers.
  2. Hallucination flag — mark fields where the LLM cited no source
     evidence. These are flagged for human review, not silently accepted.
  3. Response length cap — truncate runaway responses.
  4. Forbidden content check — reject responses that contain the LLM's
     own instructions, system prompt fragments, or API key patterns.

ABSOLUTE RULES (never relaxed):
  - The LLM NEVER makes a final underwriting decision. Any output that
    looks like a binding decision is flagged and rejected.
  - AI outputs are always labelled as AI-generated in the response.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import LLMResponseValidationError, PromptInjectionDetectedError
from app.core.logging import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Input guardrails
# --------------------------------------------------------------------------- #

# Prompt injection patterns — common jailbreak / instruction-hijack attempts
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(system\s+prompt|instructions?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+(now\s+)?a?\s*(different|new)\s+(ai|assistant|model)", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|\[SYS\]|\[/SYS\]", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+(are|were)\s+)?an?\s+\w+\s+(without|that\s+ignores?)", re.IGNORECASE),
    re.compile(r"jailbreak|dan\s+mode|developer\s+mode|unrestricted\s+mode", re.IGNORECASE),
    re.compile(r"print\s+your\s+(system\s+)?instructions|reveal\s+your\s+prompt", re.IGNORECASE),
]

# PII patterns to redact before sending to LLM
# We only redact patterns that serve NO insurance purpose
_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Social Security Numbers (US)
    (re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"), "[SSN-REDACTED]"),
    # Credit/debit card numbers (basic 16-digit pattern)
    (re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[CARD-REDACTED]"),
    # Bank routing numbers (9 digits starting with 0-3)
    (re.compile(r"\b[0-3]\d{8}\b"), "[ROUTING-REDACTED]"),
    # API keys / long hex secrets (32+ hex chars — likely credentials)
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "[SECRET-REDACTED]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), "Bearer [TOKEN-REDACTED]"),
]

# Forbidden patterns in LLM output — signs of prompt leakage or bad responses
_FORBIDDEN_OUTPUT_PATTERNS: list[re.Pattern] = [
    re.compile(r"GROQ_API_KEY|groq_api_key", re.IGNORECASE),
    re.compile(r"SECRET_KEY|secret_key", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE),
    # Absolute decision language — LLM must not make binding decisions
    re.compile(r"\b(i\s+hereby\s+(approve|deny|decline|bind)|this\s+policy\s+is\s+(approved|denied))\b", re.IGNORECASE),
]

# Token budget constants (approximate — 1 token ≈ 4 chars for English)
CHARS_PER_TOKEN_APPROX = 4
SYSTEM_PROMPT_RESERVE_TOKENS = 500   # reserve for system prompt
RESPONSE_RESERVE_TOKENS = 1024       # reserve for response


def check_injection(text: str, document_id: str | None = None) -> None:
    """
    Scan text for prompt injection patterns.

    Raises PromptInjectionDetectedError if any pattern matches.
    This function is called on ALL document text before it enters a prompt.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "Prompt injection detected",
                document_id=document_id,
                pattern=pattern.pattern[:60],
            )
            raise PromptInjectionDetectedError(document_id=document_id)


def redact_pii(text: str) -> tuple[str, int]:
    """
    Apply PII redaction patterns to text.

    Returns (redacted_text, redaction_count).
    """
    count = 0
    for pattern, replacement in _PII_PATTERNS:
        new_text, n = pattern.subn(replacement, text)
        count += n
        text = new_text
    if count > 0:
        logger.info("PII redacted before LLM call", count=count)
    return text, count


def enforce_token_budget(
    text: str,
    max_tokens: int,
    reserved_tokens: int = SYSTEM_PROMPT_RESERVE_TOKENS + RESPONSE_RESERVE_TOKENS,
) -> tuple[str, bool]:
    """
    Truncate text to fit within the available token budget.

    Strategy: keep the first 70% and last 30% of the available chars,
    with a clear truncation marker in the middle. This preserves document
    headers (most important for classification/extraction) and footers
    (signatures, dates).

    Returns (possibly_truncated_text, was_truncated).
    """
    available_chars = (max_tokens - reserved_tokens) * CHARS_PER_TOKEN_APPROX
    if len(text) <= available_chars:
        return text, False

    head_chars = int(available_chars * 0.70)
    tail_chars = int(available_chars * 0.30)
    marker = "\n\n[... TEXT TRUNCATED TO FIT TOKEN BUDGET ...]\n\n"

    truncated = text[:head_chars] + marker + text[-tail_chars:]
    logger.info(
        "Document text truncated for LLM token budget",
        original_chars=len(text),
        truncated_chars=len(truncated),
        max_tokens=max_tokens,
    )
    return truncated, True


def sanitise_input(
    text: str,
    max_tokens: int | None = None,
    document_id: str | None = None,
) -> tuple[str, dict]:
    """
    Apply all input guardrails in order:
      1. Injection check (raises on match)
      2. PII redaction
      3. Token budget enforcement

    Returns (sanitised_text, guardrail_metadata_dict).
    """
    from app.core.config import get_settings
    settings = get_settings()

    max_tok = max_tokens or settings.llm_max_tokens

    check_injection(text, document_id=document_id)
    text, pii_count = redact_pii(text)
    text, was_truncated = enforce_token_budget(text, max_tok)

    return text, {
        "pii_redactions": pii_count,
        "was_truncated": was_truncated,
    }


# --------------------------------------------------------------------------- #
# Output guardrails
# --------------------------------------------------------------------------- #

@dataclass
class GuardrailResult:
    """Result of output guardrail checks."""
    passed: bool
    content: str                          # possibly modified content
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    was_truncated: bool = False


MAX_OUTPUT_CHARS = 50_000  # ~12 500 tokens — hard cap on response length


def check_output(
    content: str,
    expected_type: str = "text",   # "text" | "json"
) -> GuardrailResult:
    """
    Apply all output guardrails to an LLM response.

    Checks:
      1. Forbidden content patterns (credentials, decision language)
      2. Response length cap
      3. For JSON responses: valid JSON structure

    Returns GuardrailResult. If passed=False, the caller must NOT use
    the content and should log the violation.
    """
    violations: list[str] = []
    warnings: list[str] = []
    was_truncated = False

    # 1. Forbidden output patterns
    for pattern in _FORBIDDEN_OUTPUT_PATTERNS:
        if pattern.search(content):
            violations.append(
                f"Forbidden pattern in LLM output: {pattern.pattern[:60]}"
            )
            logger.error(
                "Forbidden pattern detected in LLM output",
                pattern=pattern.pattern[:60],
            )

    # 2. Length cap
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS]
        was_truncated = True
        warnings.append(
            f"LLM response truncated from original length to {MAX_OUTPUT_CHARS} chars."
        )

    # 3. JSON validation
    if expected_type == "json" and content.strip():
        import json
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            violations.append(f"LLM returned invalid JSON: {exc}")

    passed = len(violations) == 0
    return GuardrailResult(
        passed=passed,
        content=content,
        violations=violations,
        warnings=warnings,
        was_truncated=was_truncated,
    )


def validate_json_output(
    content: str,
    required_keys: list[str] | None = None,
) -> dict:
    """
    Parse and validate JSON from LLM output.

    Args:
        content:       Raw LLM response string.
        required_keys: Keys that must be present in the parsed dict.

    Returns:
        Parsed dict.

    Raises:
        LLMResponseValidationError: Invalid JSON or missing required keys.
    """
    import json

    # Strip common LLM formatting artifacts
    stripped = content.strip()
    if stripped.startswith("```json"):
        stripped = stripped[7:]
    if stripped.startswith("```"):
        stripped = stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    stripped = stripped.strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMResponseValidationError(
            f"LLM returned invalid JSON: {exc}. Raw (first 300 chars): {content[:300]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise LLMResponseValidationError(
            f"Expected JSON object, got {type(parsed).__name__}"
        )

    if required_keys:
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            raise LLMResponseValidationError(
                f"LLM JSON response missing required keys: {missing}"
            )

    return parsed


def add_ai_disclaimer(text: str) -> str:
    """
    Prepend the mandatory AI-generated content disclaimer.

    Per the steering file: all AI outputs must be clearly labelled.
    This is called on summaries and explanations before they are stored.
    """
    disclaimer = (
        "[AI-GENERATED CONTENT — For underwriter review only. "
        "Not a binding decision or approved policy position.] "
    )
    return disclaimer + text
