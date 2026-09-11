# INSIGHT AI — Architecture Steering File

## DIRECTORY STRUCTURE

```
commercial_submission_ai/
├── backend/
│   └── app/
│       ├── api/            # FastAPI routers — thin HTTP layer only
│       │   ├── v1/
│       │   │   ├── auth.py
│       │   │   ├── submissions.py
│       │   │   ├── documents.py
│       │   │   ├── knowledge.py
│       │   │   ├── users.py
│       │   │   └── analytics.py
│       │   └── deps.py     # Shared dependencies (auth, db session)
│       ├── core/           # Configuration, logging, exceptions, constants
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── exceptions.py
│       │   └── constants.py
│       ├── models/         # SQLAlchemy ORM models
│       ├── schemas/        # Pydantic request/response schemas
│       ├── services/       # Business logic — orchestrates repositories + AI
│       ├── repositories/   # Database access layer — all raw DB queries here
│       ├── ai/             # LLM abstraction layer
│       │   ├── provider.py         # Abstract LLMProvider interface
│       │   ├── groq_provider.py    # Groq implementation
│       │   └── schemas.py          # LLM input/output Pydantic schemas
│       ├── rag/            # RAG subsystem
│       │   ├── chunker.py
│       │   ├── embeddings.py
│       │   ├── vector_store.py
│       │   └── retriever.py
│       ├── ingestion/      # File validation and ingestion
│       ├── extraction/     # Document-type-specific extraction logic
│       ├── validation/     # Deterministic validation rules
│       ├── risk/           # Transparent risk scoring engine
│       ├── auth/           # JWT, password hashing, RBAC
│       ├── database/       # SQLAlchemy setup and session management
│       ├── utils/          # Shared utilities
│       └── main.py         # FastAPI application factory
├── frontend/
│   └── src/
│       ├── components/     # Reusable UI components
│       ├── pages/          # Page-level components
│       ├── layouts/        # Shell/sidebar/navigation layouts
│       ├── features/       # Feature modules (submissions, documents, etc.)
│       ├── services/       # API call functions — no business logic in components
│       ├── hooks/          # Custom React hooks
│       ├── types/          # TypeScript type definitions
│       ├── utils/          # Pure utility functions
│       └── auth/           # Auth context, protected routes, token management
├── prompts/                # Versioned prompt files
│   ├── extraction/
│   ├── classification/
│   ├── summarization/
│   ├── risk_explanation/
│   ├── rag/
│   └── guardrails/
├── data/
│   ├── raw/strata_insurance_corpus/
│   ├── processed/
│   └── output/
├── docs/
│   ├── ARCHITECTURE.md
│   └── PROJECT_PROGRESS.md
├── tests/
├── .kiro/steering/
├── .env.example
├── .gitignore
└── README.md
```

---

## LAYERING RULES

1. **API routers** — HTTP only. No business logic. Delegate to services.
2. **Services** — Business logic, orchestration. No direct DB queries.
3. **Repositories** — All database access. No business logic.
4. **Models** — SQLAlchemy ORM definitions only.
5. **Schemas** — Pydantic request/response validation only.
6. **AI layer** — All LLM calls through `LLMProvider` abstraction. Never call Groq directly from services.
7. **RAG layer** — Vector retrieval, chunking, embedding — isolated from extraction logic.
8. **Validation** — Deterministic Python rules. LLM may explain but never calculate.
9. **Risk** — Transparent scoring engine. Configurable thresholds. LLM explains, Python calculates.

---

## API RESPONSE ENVELOPE

All API responses follow this structure:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "request_id": "uuid-v4"
}
```

Error responses:
```json
{
  "success": false,
  "data": null,
  "error": { "code": "VALIDATION_ERROR", "message": "Human-readable message" },
  "request_id": "uuid-v4"
}
```

Stack traces are NEVER returned to the client.

---

## SUBMISSION PROCESSING STATES

```
UPLOADED → VALIDATING → PARSING → OCR_PROCESSING → CLASSIFYING
→ EXTRACTING → VALIDATING_DATA → RETRIEVING_GUIDELINES → ANALYZING
→ READY_FOR_REVIEW → UNDER_REVIEW → COMPLETED | FAILED
```

---

## KEY API ENDPOINTS

```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/submissions
GET    /api/v1/submissions
GET    /api/v1/submissions/{id}
POST   /api/v1/submissions/{id}/documents
POST   /api/v1/documents/{id}/process
GET    /api/v1/submissions/{id}/extraction
GET    /api/v1/submissions/{id}/validation
GET    /api/v1/submissions/{id}/risk
GET    /api/v1/submissions/{id}/summary
GET    /api/v1/submissions/{id}/evidence
POST   /api/v1/submissions/{id}/underwriter-decision
POST   /api/v1/knowledge-documents
GET    /api/v1/knowledge-documents
POST   /api/v1/knowledge-documents/{id}/approve
POST   /api/v1/knowledge-documents/{id}/index
GET    /api/v1/health
```
