# Prompt Management

All LLM prompts are stored here, organized by purpose and versioned.

## Structure

```
prompts/
  extraction/       ← Document-type extraction prompts
  classification/   ← Document classification prompts
  summarization/    ← Underwriter summary prompts
  risk_explanation/ ← Risk score explanation prompts
  rag/              ← RAG-assisted reasoning prompts
  guardrails/       ← System-level safety prompt fragments
```

## Prompt File Format

Every prompt file includes a metadata header:

```
# name: <prompt name>
# version: <semver e.g. 1.0.0>
# purpose: <description>
# inputs: <variables injected — e.g. {document_text}, {company_name}>
# outputs: <expected output schema name>
# safety_rules: <LLM constraints applied>
# last_updated: <ISO date>
```

## Loading

Prompts are loaded by the `PromptManager` service (`backend/app/services/prompt_manager.py`)
using name + version. Application logic references prompts by name — not by file path.
This allows prompt updates without changing business logic.

## Rules

- Never scatter prompt strings directly in service or API code
- Prompts are DATA, not code — they can be updated without a deployment in future
- System instruction fragments live in `guardrails/` and are prepended to all LLM calls
- The system instruction fragment explicitly labels document content as UNTRUSTED DATA
