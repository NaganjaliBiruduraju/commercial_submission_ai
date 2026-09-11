# INSIGHT AI — Commercial Submission Intelligence

> Enterprise AI-powered insurance document intelligence and underwriting support system.

---

## What This Is

INSIGHT AI transforms unstructured commercial insurance submission documents into structured,
explainable underwriting insights. It supports — but never replaces — human underwriting decisions.

**Core principle:**
```
Unstructured Documents → Trusted Extraction → Structured Data → Validation
→ Evidence → Relevant Knowledge → Controlled AI Reasoning
→ Explainable Insight → Human Underwriter Decision
```

The LLM is one component of the system. It is not the entire system.

---

## Key Capabilities

| Capability | Description |
|---|---|
| Document Intelligence | Parse PDF, DOCX, XLSX, CSV, JPG/PNG including scanned documents |
| Structured Extraction | LLM extracts fields into strict JSON schema with evidence mapping |
| Deterministic Validation | Python rules detect conflicts, missing info, and invalid data |
| RAG Retrieval | Retrieve relevant underwriting guidelines from approved knowledge base |
| Risk Scoring | Transparent, configurable risk engine — Python calculates, LLM explains |
| Audit Trail | Every change tracked: who, what, when, why |
| Human Control | Underwriter reviews, overrides, and makes the final decision |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 |
| Database | PostgreSQL 15 + pgvector |
| AI | Groq API (abstracted — swappable) |
| Embeddings | sentence-transformers (local, free) |
| OCR | Tesseract via pytesseract |
| Frontend | React 18, TypeScript 5, Vite 5, Tailwind CSS, shadcn/ui |
| Auth | JWT (python-jose), bcrypt |

---

## Project Structure

```
commercial_submission_ai/
├── backend/              # FastAPI backend
│   └── app/
│       ├── api/          # Route handlers (thin HTTP layer)
│       ├── core/         # Config, logging, exceptions
│       ├── models/       # SQLAlchemy ORM models
│       ├── schemas/      # Pydantic schemas
│       ├── services/     # Business logic
│       ├── repositories/ # Database access
│       ├── ai/           # LLM abstraction layer
│       ├── rag/          # RAG subsystem
│       ├── ingestion/    # File validation and ingestion
│       ├── extraction/   # Document-type extraction
│       ├── validation/   # Deterministic validation rules
│       ├── risk/         # Risk scoring engine
│       ├── auth/         # JWT and RBAC
│       └── database/     # SQLAlchemy setup
├── frontend/             # React frontend
│   └── src/
│       ├── pages/        # Page components
│       ├── features/     # Feature modules
│       ├── services/     # API service layer
│       ├── components/   # Reusable components
│       └── types/        # TypeScript types
├── prompts/              # Versioned LLM prompts
├── data/                 # Raw, processed, output data
├── docs/                 # Architecture and progress documentation
├── tests/                # Automated tests
└── .kiro/steering/       # Kiro AI guidance files
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+ with pgvector extension
- Tesseract OCR

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux

pip install -r requirements.txt

# Copy and configure environment
cp ../.env.example ../.env
# Edit .env — fill in DATABASE_URL, SECRET_KEY, GROQ_API_KEY

# Run database migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install

# Copy frontend env (no secrets — just API URL)
cp ../.env.example .env.local
# Set VITE_API_BASE_URL=http://localhost:8000/api/v1

npm run dev
```

### Health Check

```
GET http://localhost:8000/api/v1/health
```

---

## Environment Variables

See `.env.example` for all required variables with descriptions.

**Required before first run:**
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — Generate: `openssl rand -hex 32`
- `GROQ_API_KEY` — Your Groq API key (server-side only, never in frontend)

---

## Security Notes

- The React frontend **never** communicates with Groq directly
- All LLM calls happen server-side in FastAPI
- Uploaded documents are treated as **untrusted content**
- Prompt injection protection is implemented at the application layer
- Every important action is audited

---

## Development Phases

See `docs/PROJECT_PROGRESS.md` for phase-by-phase progress.

---

## License

See `LICENSE` file.

---

> **⚠ IMPORTANT:** This system assists human underwriters. It does not make autonomous
> underwriting decisions. Final decisions must be made by an authorized human underwriter.
