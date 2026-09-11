# INSIGHT AI — Development Rules Steering File

## CORE DEVELOPMENT PRINCIPLES

1. **Correctness over speed** — never optimize for "how quickly can we generate code"
2. **Security is non-negotiable** — never sacrifice security to simplify demos
3. **Explainability is a first-class requirement** — every AI-derived fact must be traceable
4. **Human control is mandatory** — the system assists, the human decides
5. **Deterministic before AI** — use Python where Python is correct; use AI where AI is needed

---

## WHAT USES PYTHON (NOT LLM)

- Date comparison and validation
- Revenue comparison between documents
- Required field validation
- File extension/MIME validation
- Risk score arithmetic
- Database authorization
- Employee count validation
- Document existence checks
- Numerical range validation

## WHAT USES LLM

- Unstructured text extraction
- Semantic document classification
- Natural language summarization
- Reasoning over RAG context
- Explanation of risk factors
- Natural language interpretation of ambiguous content

---

## GIT WORKFLOW (MANDATORY)

For every completed phase:
```
IMPLEMENT → TEST → LINT → TYPE CHECK → SECURITY CHECK
→ REVIEW DIFF → UPDATE DOCS → GIT COMMIT → GIT PUSH → MARK COMPLETE
```

### Commit Message Format (Conventional Commits)
- `chore:` — setup, infrastructure, non-feature
- `feat:` — new feature
- `fix:` — bug fix
- `security:` — security improvement
- `test:` — test additions
- `docs:` — documentation
- `refactor:` — code reorganization without behavior change

NEVER use: "changes", "update", "fixed stuff", "final", "working", "done"

### Never Commit
- `.env` files
- API keys or secrets
- Passwords
- JWT secrets
- `node_modules/`
- Python virtual environments
- `__pycache__/`
- Build artifacts (`dist/`, `build/`)
- Uploaded user documents
- Local database files

### Never Push
- Broken tests
- Non-starting backend
- Non-building frontend
- Exposed secrets
- Unresolved TypeScript or Python errors

---

## PHASE COMPLETION GATE

A phase is ONLY complete when ALL of the following pass:
- [ ] Implementation complete per phase requirements
- [ ] Relevant unit tests pass
- [ ] Backend starts without errors
- [ ] Frontend builds without errors (from Phase 13 onward)
- [ ] `git status` shows no unexpected files
- [ ] `git diff --staged` shows no secrets
- [ ] PROJECT_PROGRESS.md updated
- [ ] Meaningful commit created
- [ ] Pushed to origin

If any gate fails: status = BLOCKED. Report clearly. Do not proceed.

---

## BLOCKED PHASE REPORT FORMAT

```
PHASE STATUS: BLOCKED
PHASE: <number and name>
REASON: <clear explanation>
FAILED CHECKS: <list>
REQUIRED ACTION: <what is needed to unblock>
```

---

## PHASE COMPLETION REPORT FORMAT

```
PHASE: <number — name>
STATUS: COMPLETED
WHAT WAS BUILT: <summary>
FILES CREATED: <list>
FILES MODIFIED: <list>
TESTS: PASS / FAIL / NOT YET APPLICABLE
LINT: PASS / FAIL
BUILD: PASS / FAIL
SECURITY CHECK: PASS / FAIL
GIT COMMIT: <hash — message>
GIT PUSH: PUSHED / NOT PUSHED
NEXT PHASE: <number — name>
```

---

## PROMPT MANAGEMENT

Prompts live in `prompts/` at the project root, organized by purpose:
```
prompts/
  extraction/
  classification/
  summarization/
  risk_explanation/
  rag/
  guardrails/
```

Each prompt file includes header metadata:
```
# name: <prompt name>
# version: <semver>
# purpose: <description>
# inputs: <what fields are injected>
# outputs: <expected output schema>
# safety_rules: <LLM constraints applied>
```

Prompts are loaded by name/version at runtime — not hardcoded into service logic.

---

## RISK ANALYSIS RULES

- Risk score is calculated by Python — not by the LLM
- LLM may generate an explanation of the score
- All thresholds are configurable — never hard-coded
- Risk factors: loss_frequency, loss_severity, loss_trend, revenue_exposure,
  industry_exposure, location_exposure, financial_indicators,
  missing_information_penalty, conflict_penalty, coverage_complexity
- Score ranges: 0–100
- Categories: LOW (0–39), MEDIUM (40–69), HIGH (70–100) — configurable
- Demo rules are clearly labelled: [DEMO RULE — NOT APPROVED POLICY]

---

## EVIDENCE SYSTEM

Every AI-derived important field must have a source evidence object:
```json
{
  "field_name": "annual_revenue",
  "value": 25000000,
  "confidence": 0.95,
  "evidence": {
    "document_id": "uuid",
    "document_name": "acord_125.pdf",
    "page_number": 2,
    "section": "Financial Information",
    "source_text": "Annual Revenue: $25,000,000",
    "extraction_timestamp": "2025-01-01T00:00:00Z"
  }
}
```

The UI must allow navigation from an extracted field to the source evidence.
The LLM is FORBIDDEN from fabricating evidence references.

---

## DEMO DATA RULES

Demo data is clearly labelled: `[SYNTHETIC DEMO DATA — NOT REAL INSURANCE DATA]`

Demo submission:
- Applicant: ABC Manufacturing LLC
- Revenue (ACORD): $25M — Revenue (Financial Statement): $30M [DELIBERATE CONFLICT]
- Employees: 185, Locations: 4
- Coverage: General Liability, Property, Workers Compensation
- Loss History: 2023: 2 claims $50K | 2024: 1 claim $15K | 2025: 3 claims $175K

The system must detect the $25M vs $30M conflict through deterministic validation.
This demo conflict is intentional to validate the conflict detection subsystem.

---

## RAG RULES

- Only documents with status = ACTIVE may be retrieved as underwriting guidance
- Submission documents CANNOT be retrieved as underwriting guidelines
- Every retrieved chunk retains: document_id, title, category, version, page, section
- Final summary must cite which guideline influenced each recommendation
- Embedding provider is abstracted — not hard-coded

---

## DO NOT

- Ask unnecessary questions (decisions made by standard engineering practice are documented here)
- Invent insurance underwriting rules — mark as [CONFIGURATION REQUIRED]
- Hard-code risk thresholds
- Present DEMO RULE as real insurance policy
- Use the LLM for deterministic calculations
- Make the first version agentic — build deterministic pipeline first
- Put business logic in React components
- Put all backend logic in main.py
- Call Groq directly outside of `groq_provider.py`
- Store any secret in any source file
