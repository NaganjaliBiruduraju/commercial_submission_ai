# INSIGHT AI — System Architecture

**Product:** INSIGHT AI — Commercial Submission Intelligence  
**Version:** 1.0  
**Status:** Phase 1 — Foundation  

---

## 1. SYSTEM OVERVIEW

INSIGHT AI is an enterprise-grade Insurance Document Intelligence and Underwriting Support
system. It transforms unstructured commercial insurance submission documents into structured,
explainable insights that support — but never replace — human underwriting decisions.

### Core Principle

```
UNSTRUCTURED DOCUMENTS
        ↓
TRUSTED EXTRACTION
        ↓
STRUCTURED DATA
        ↓
DETERMINISTIC VALIDATION
        ↓
EVIDENCE MAPPING
        ↓
RELEVANT KNOWLEDGE (RAG)
        ↓
CONTROLLED AI REASONING
        ↓
EXPLAINABLE INSIGHT
        ↓
HUMAN UNDERWRITER DECISION
```

The LLM is **one component** of this pipeline. It is not the entire system.

---

## 2. HIGH-LEVEL ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        REACT FRONTEND                           │
│  (TypeScript + Vite + Tailwind + shadcn/ui)                     │
│                                                                 │
│  Dashboard │ Submissions │ Documents │ Knowledge Base │         │
│  Analytics │ Guidelines  │ Users     │ Settings       │         │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS + JWT
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                            │
│                                                                 │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │   API   │  │ Services │  │  Repos   │  │    Database    │  │
│  │ Routers │→ │ (Logic)  │→ │  (Data)  │→ │  PostgreSQL    │  │
│  └─────────┘  └──────────┘  └──────────┘  └────────────────┘  │
│                    │                                            │
│          ┌─────────┼──────────────────────────────────┐        │
│          ▼         ▼                    ▼              ▼        │
│   ┌──────────┐ ┌────────┐       ┌──────────┐   ┌──────────┐   │
│   │  AI      │ │  RAG   │       │Validation│   │  Risk    │   │
│   │ Service  │ │System  │       │  Engine  │   │  Engine  │   │
│   └──────────┘ └────────┘       └──────────┘   └──────────┘   │
│        │            │                                           │
│        ▼            ▼                                           │
│   ┌─────────┐  ┌─────────┐                                     │
│   │  Groq   │  │pgvector │                                     │
│   │  API    │  │(vectors)│                                     │
│   └─────────┘  └─────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
```

**Security boundary:** The React frontend never communicates with Groq.
All LLM calls happen server-side inside the FastAPI backend.

---

## 3. DOCUMENT PROCESSING PIPELINE

### 3.1 Ingestion and Parsing

```
Uploaded File
     ↓
[INPUT GUARDRAIL]
  • MIME type validation (whitelist)
  • File size check (configurable max, default 50MB)
  • File count check (configurable max, default 20/submission)
  • Corruption detection
     ↓
[PARSER SELECTION]
  PDF (text)    → pdfplumber  → text + tables
  PDF (scanned) → PyMuPDF → page images → Tesseract OCR
  DOCX          → python-docx → paragraphs + tables + headings
  XLSX          → openpyxl    → sheets + rows + structured tables
  CSV           → pandas      → structured tabular data
  JPG/PNG       → pytesseract → OCR text + optional vision
     ↓
[PARSED CONTENT]
  text_content: str
  tables: list[dict]
  metadata: dict (page_count, author, created_at, etc.)
  raw_pages: list[str]  (for page-level evidence mapping)
```

### 3.2 Classification

```
Parsed Content + Filename + Metadata
     ↓
[DETERMINISTIC CLASSIFIER]
  • Keyword matching (ACORD form numbers, header patterns)
  • Filename pattern matching
  • Page layout analysis
     ↓ (if low confidence)
[LLM CLASSIFIER]
  • Classifies among known document types
  • Returns: document_type, confidence, classification_reason
     ↓
Document Types:
  ACORD_APPLICATION | ACORD_GL | ACORD_PROPERTY | ACORD_AUTO
  ACORD_WORKERS_COMP | LOSS_RUN | FINANCIAL_STATEMENT
  BROKER_EMAIL | UNDERWRITING_GUIDELINE | CLAIMS_DOCUMENT
  EVIDENCE_PHOTO | IDENTITY_DOCUMENT | OTHER
```

### 3.3 Extraction

```
Classified Document + Parsed Content
     ↓
[DOCUMENT-SPECIFIC EXTRACTOR]
  ACORD_APPLICATION → extract applicant, revenue, employees, locations
  LOSS_RUN          → extract claims: date, type, amount, reserve, status
  FINANCIAL_STMT    → extract revenue, expenses, assets, liabilities
  BROKER_EMAIL      → extract coverage requests, limits, effective date
  (etc.)
     ↓
[LLM STRUCTURED EXTRACTION]
  System Prompt:   SYSTEM INSTRUCTIONS (trusted, application-defined)
  Task Prompt:     TASK INSTRUCTIONS (trusted, application-defined)
  Document Data:   [UNTRUSTED DOCUMENT DATA — labelled clearly]
  Output Schema:   Strict Pydantic/JSON Schema
     ↓
[OUTPUT GUARDRAIL]
  • Validate against strict Pydantic schema
  • Reject unexpected fields
  • Validate numerical types and ranges
  • Validate dates
  • Verify evidence citations exist
     ↓
[EVIDENCE MAPPING]
  Each extracted field gets:
  { field_name, value, confidence, source_document, page, section, source_text }
```

### 3.4 Deterministic Validation

```
Extracted Fields from All Documents
     ↓
[PYTHON VALIDATION ENGINE]
  • Revenue comparison: ACORD vs Financial Statement
  • Date logic: effective_date < expiration_date
  • Employee count: >= 0
  • Required fields: company_name, business_type, at minimum
  • Identity consistency: company name across all documents
  • Coverage-specific requirements: e.g., WC requires payroll data
     ↓
ValidationIssue records:
  type: CONFLICT | MISSING | INVALID | WARNING
  severity: ERROR | WARNING | INFO
  field_name, description, affected_documents, suggested_action
```

---

## 4. RAG PIPELINE

```
Knowledge Document (Underwriting Guideline, Policy, etc.)
     ↓
[TEXT EXTRACTION] (same parsers as document pipeline)
     ↓
[CLEANING] (normalize whitespace, remove headers/footers)
     ↓
[CHUNKING] (sliding window, ~500 tokens, 50-token overlap)
     ↓
[METADATA ATTACHMENT]
  { document_id, title, category, version, effective_date, section }
     ↓
[EMBEDDING GENERATION]
  Embedding Provider (abstracted — default: sentence-transformers)
  Text → float[384] vector (or configured dimension)
     ↓
[VECTOR STORAGE]
  PostgreSQL + pgvector extension
  Table: knowledge_chunks (id, document_id, chunk_text, embedding, metadata)
     ↓
━━━━━━━━━━━━━━━━━━ RETRIEVAL (at inference time) ━━━━━━━━━━━━━━━━━━
     ↓
[QUERY EMBEDDING] (query text → vector)
     ↓
[RETRIEVAL GUARDRAIL]
  Only chunks from documents with status = ACTIVE
  Only chunks where effective_date <= today <= expiration_date
     ↓
[SIMILARITY SEARCH] (cosine similarity, top-k configurable)
     ↓
[RETRIEVED CHUNKS + METADATA]
     ↓
[LLM CONTEXT ASSEMBLY]
  System:   Trusted system instructions
  Task:     Specific reasoning task
  Data:     [UNTRUSTED DOCUMENT DATA]
  Context:  [APPROVED UNDERWRITING GUIDELINES: source, version, section]
     ↓
[LLM REASONING]
     ↓
[OUTPUT GUARDRAIL + SCHEMA VALIDATION]
```

---

## 5. LLM ABSTRACTION LAYER

```python
# All LLM calls use this interface — never call Groq directly from services

class LLMProvider(ABC):
    async def generate_structured(
        self,
        system_prompt: str,        # Trusted — application-controlled
        task_prompt: str,          # Trusted — application-controlled
        document_data: str,        # UNTRUSTED — labelled as data
        output_schema: dict,       # JSON Schema for strict output
        rag_context: str | None,   # Only from ACTIVE approved documents
        model_params: ModelParams, # temperature, max_tokens, etc.
    ) -> StructuredLLMResponse: ...

# Current implementation
class GroqLLMProvider(LLMProvider): ...

# Future implementations — drop-in replacements
# class OpenAILLMProvider(LLMProvider): ...
# class AnthropicLLMProvider(LLMProvider): ...
# class AzureOpenAILLMProvider(LLMProvider): ...
```

---

## 6. RISK SCORING ENGINE

Risk is calculated by **Python** — the LLM only generates the explanation text.

```
RISK SCORE CALCULATION (Python — deterministic, configurable)

Base Score: 50  [CONFIGURABLE]

Positive risk factors (increase score):
  + loss_frequency_factor    (based on claim count per year)
  + loss_severity_factor     (based on total incurred losses)
  + loss_trend_factor        (is severity increasing year-over-year?)
  + revenue_discrepancy      (ACORD vs Financial Statement mismatch)
  + missing_information      (required fields absent)
  + conflict_penalty         (number of detected conflicts)
  + industry_exposure        [CONFIGURATION REQUIRED — no invented rules]
  + coverage_complexity      (number and type of coverage lines)

Negative risk factors (decrease score):
  - stable_financials        (consistent revenue, no discrepancies)
  - loss_free_years          (no claims in recent period)
  - complete_information     (all required fields present)

Final Score: 0–100
Category:
  LOW     (0–39)   [CONFIGURABLE THRESHOLD]
  MEDIUM  (40–69)  [CONFIGURABLE THRESHOLD]
  HIGH    (70–100) [CONFIGURABLE THRESHOLD]

Risk score thresholds are loaded from configuration — NEVER hard-coded.
Rules not provided by approved guidelines are marked: [CONFIGURATION REQUIRED]
Demo rules are clearly marked: [DEMO RULE — NOT APPROVED POLICY]
```

---

## 7. DATABASE SCHEMA (Core Entities)

```
users ──────────────────────────────────────────── roles
  id (UUID PK)                                      id (UUID PK)
  email (unique)                                    name (ADMIN|UNDERWRITER|REVIEWER)
  hashed_password                                   permissions (JSON)
  role_id (FK → roles)
  is_active
  created_at, updated_at

submissions ──────────────── documents
  id (UUID PK)               id (UUID PK)
  submission_number          submission_id (FK)
  applicant_name             document_type (enum)
  broker_name                original_filename
  status (enum)              stored_filename (UUID)
  assigned_to (FK → users)   file_size
  created_by (FK → users)    mime_type
  created_at, updated_at     processing_status (enum)
                             classification_confidence
                             created_at, updated_at

extracted_fields ──────────────── evidence
  id (UUID PK)                    id (UUID PK)
  submission_id (FK)              extracted_field_id (FK)
  document_id (FK)                document_id (FK)
  field_name                      document_name
  field_value (JSON)              page_number
  confidence                      section
  is_overridden                   source_text
  override_value (JSON)           extraction_timestamp
  override_by (FK → users)
  override_at
  created_at

validation_issues                 risk_assessments
  id (UUID PK)                    id (UUID PK)
  submission_id (FK)              submission_id (FK)
  issue_type (enum)               risk_score (int 0-100)
  severity (enum)                 risk_category (enum)
  field_name                      score_breakdown (JSON)
  description                     score_explanation (text)
  affected_documents (JSON)       calculated_at
  is_resolved                     calculated_by_model
  resolved_by (FK → users)        created_at
  resolved_at

knowledge_documents ─────── knowledge_chunks          underwriter_decisions
  id (UUID PK)                id (UUID PK)               id (UUID PK)
  title                       document_id (FK)            submission_id (FK)
  category                    chunk_text                  decision (enum)
  version                     chunk_index                 decision_notes
  effective_date              page_number                 decided_by (FK → users)
  expiration_date             section                     decided_at
  status (enum)               embedding (vector)          created_at
  approved_by (FK → users)    metadata (JSON)
  stored_filename             created_at
  created_at, updated_at

audit_logs
  id (UUID PK)
  action (enum)
  entity_type
  entity_id (UUID)
  actor_id (FK → users)
  old_value (JSON)
  new_value (JSON)
  reason (text)
  ip_address
  created_at
```

---

## 8. FRONTEND ARCHITECTURE

```
frontend/src/
  auth/
    AuthContext.tsx       ← JWT token management, user state
    ProtectedRoute.tsx    ← Route-level access control
    useAuth.ts            ← Auth hook

  layouts/
    AppShell.tsx          ← Sidebar + header wrapper
    Sidebar.tsx           ← Navigation
    TopBar.tsx            ← User menu, notifications

  pages/
    LoginPage.tsx
    DashboardPage.tsx
    SubmissionsPage.tsx
    SubmissionDetailPage.tsx
    DocumentsPage.tsx
    KnowledgeBasePage.tsx
    AnalyticsPage.tsx
    UsersPage.tsx
    SettingsPage.tsx

  features/
    submissions/          ← Submission list, create, status
    documents/            ← Upload, classify, process
    extraction/           ← View extracted fields + evidence
    validation/           ← Missing info, conflicts
    risk/                 ← Risk score display, breakdown
    summary/              ← Underwriter summary
    knowledge/            ← Knowledge base management
    review/               ← Human review workflow

  services/
    api.ts                ← Axios instance, interceptors, auth header
    submissions.ts        ← Submission API calls
    documents.ts          ← Document API calls
    knowledge.ts          ← Knowledge base API calls
    auth.ts               ← Login, refresh, logout

  components/
    ui/                   ← shadcn/ui base components
    evidence/             ← EvidencePanel, EvidenceBadge
    risk/                 ← RiskScoreCard, RiskBreakdown
    validation/           ← ConflictAlert, MissingInfoPanel
    shared/               ← StatusBadge, ConfidenceBadge, etc.

  hooks/
    useSubmission.ts
    useDocuments.ts
    useValidation.ts
    useRiskAssessment.ts

  types/
    index.ts              ← All TypeScript interfaces matching backend schemas
```

---

## 9. SECURITY ARCHITECTURE

```
┌─────────────────────────────────────────────┐
│              SECURITY LAYERS                │
│                                             │
│  1. HTTPS (TLS) — transport layer           │
│  2. JWT Authentication — every API call     │
│  3. RBAC — role checked per endpoint        │
│  4. Input validation — Pydantic schemas     │
│  5. File validation — MIME + size + type    │
│  6. Prompt injection detection — pre-LLM    │
│  7. Output validation — post-LLM schema     │
│  8. SQL injection protection — ORM only     │
│  9. Audit logging — all state changes       │
│ 10. Secrets via env vars — never in code    │
└─────────────────────────────────────────────┘
```

---

## 10. HUMAN-IN-THE-LOOP

The underwriter retains full control at every step:

| AI Output                    | Underwriter Can        |
|------------------------------|------------------------|
| Extracted field              | Override + note reason |
| Validation issue             | Resolve + note reason  |
| Risk score                   | View full breakdown    |
| RAG-retrieved guideline      | View source document   |
| AI summary                   | Accept / flag          |
| Suggested recommendation     | Accept / change        |
| Final decision               | ONLY human can set     |

**The system NEVER says:** "Approved automatically." "Rejected automatically." "Bind this policy."  
**The system ALWAYS says:** "Underwriter review required." "Recommended for review." "Insufficient evidence."

---

## 11. OBSERVABILITY

Every processing stage emits a structured log entry:

```json
{
  "timestamp": "ISO8601",
  "level": "INFO|WARNING|ERROR",
  "request_id": "uuid",
  "submission_id": "uuid|null",
  "document_id": "uuid|null",
  "stage": "PARSING|OCR|CLASSIFICATION|EXTRACTION|...",
  "duration_ms": 142,
  "status": "SUCCESS|FAILURE",
  "error_code": "null|ERROR_CODE",
  "message": "human-readable description"
}
```

Secrets are **never** logged. Stack traces go to backend logs only — never to API responses.

---

## 12. PROMPT STRUCTURE

Every LLM call is assembled in this fixed order — never mixed:

```
╔══════════════════════════════════════════════════╗
║  [1] SYSTEM INSTRUCTIONS      ← TRUSTED          ║
║      Application-controlled. Never user input.   ║
╠══════════════════════════════════════════════════╣
║  [2] TASK INSTRUCTIONS        ← TRUSTED          ║
║      Specific extraction/analysis task.          ║
╠══════════════════════════════════════════════════╣
║  [3] DOCUMENT DATA            ← UNTRUSTED        ║
║      Clearly labelled as data. Sanitized.        ║
║      Prompt injection warnings active.           ║
╠══════════════════════════════════════════════════╣
║  [4] RAG CONTEXT              ← CONDITIONALLY    ║
║      Only from ACTIVE approved knowledge docs.   ║
║      Source metadata included per chunk.         ║
╚══════════════════════════════════════════════════╝
```

---

*Last updated: Phase 1 — Project Architecture*  
*See `docs/PROJECT_PROGRESS.md` for phase-by-phase progress.*
