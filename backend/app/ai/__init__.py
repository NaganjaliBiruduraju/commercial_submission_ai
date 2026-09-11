"""
AI layer — LLM integration, prompt building, and guardrails.

Public API:
  complete_text(prompt, ...)      → str
  complete_json(prompt, ...)      → dict
  complete_with_schema(prompt, schema_class, ...) → Pydantic model
  llm_is_available()              → bool
  token_estimate(text)            → int

Provider:
  get_llm_provider()              → LLMProvider
  set_llm_provider(provider)      → None  (for testing)

Guardrails:
  sanitise_input(text, ...)       → (str, dict)
  check_output(content, ...)      → GuardrailResult
  add_ai_disclaimer(text)         → str

Prompt building:
  PromptBuilder(category, name)   → builder
  build_extraction_prompt(...)    → str
  build_summarisation_prompt(...) → str
  build_risk_explanation_prompt(...) → str
"""
from app.ai.llm_client import (
    complete_text,
    complete_json,
    complete_with_schema,
    llm_is_available,
    token_estimate,
    count_tokens_precise,
)
from app.ai.provider import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMMessage,
    GroqProvider,
    get_llm_provider,
    set_llm_provider,
)
from app.ai.guardrails import (
    sanitise_input,
    check_output,
    check_injection,
    redact_pii,
    add_ai_disclaimer,
    validate_json_output,
)
from app.ai.prompt_builder import (
    PromptBuilder,
    build_extraction_prompt,
    build_summarisation_prompt,
    build_risk_explanation_prompt,
    get_template,
    SYSTEM_PROMPT,
)

__all__ = [
    # LLM client
    "complete_text",
    "complete_json",
    "complete_with_schema",
    "llm_is_available",
    "token_estimate",
    "count_tokens_precise",
    # Provider
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMMessage",
    "GroqProvider",
    "get_llm_provider",
    "set_llm_provider",
    # Guardrails
    "sanitise_input",
    "check_output",
    "check_injection",
    "redact_pii",
    "add_ai_disclaimer",
    "validate_json_output",
    # Prompt building
    "PromptBuilder",
    "build_extraction_prompt",
    "build_summarisation_prompt",
    "build_risk_explanation_prompt",
    "get_template",
    "SYSTEM_PROMPT",
]
