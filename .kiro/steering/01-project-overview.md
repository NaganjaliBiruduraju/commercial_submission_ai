# INSIGHT AI — Commercial Submission Intake
## Project Overview Steering File

**Product Name:** INSIGHT AI — Commercial Submission Intelligence  
**Purpose:** Enterprise AI-powered insurance document intelligence and underwriting support system.

---

## PRIMARY OBJECTIVE

Convert unstructured commercial insurance submission documents into reliable structured insights
that help a human underwriter understand the submission, identify missing or conflicting
information, retrieve relevant underwriting guidelines, analyze risk, and make a better-informed
underwriting decision.

The system MUST NOT make autonomous final underwriting decisions.
A human underwriter MUST remain in control of the final decision.

---

## CORE PIPELINE

```
Broker Submission → Document Upload → File Validation → Document Parsing/OCR
→ Document Classification → Information Extraction → Structured JSON
→ Source/Evidence Mapping → Deterministic Validation → Missing Information Detection
→ Conflict Detection → RAG Retrieval → Underwriting Guideline Context
→ LLM Reasoning/Explanation → Risk Analysis → Underwriter Summary
→ Human Underwriter Review → Final Decision
```

---

## TECHNOLOGY STACK

### Backend
- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0 (async)
- PostgreSQL 15+
- Alembic (migrations)

### Frontend
- React 18
- TypeScript 5
- Vite 5
- Tailwind CSS 3
- shadcn/ui
- Lucide React icons

### AI
- Groq API (provider abstraction — swappable)
- Initial model: `openai/gpt-oss-20b` via Groq
- Structured JSON output (strict mode where supported)
- RAG via PostgreSQL pgvector

### Document Processing
- pdfplumber / PyMuPDF for PDF text/tables
- python-docx for DOCX
- openpyxl for XLSX
- pandas for CSV
- Tesseract / pytesseract for OCR on scanned PDFs and images

---

## AUTHENTICATION AND ROLES

- JWT-based authentication (python-jose)
- Passwords hashed with bcrypt
- Roles: ADMIN, UNDERWRITER, REVIEWER
- All sensitive API routes are protected
- Role-based access control enforced at the API layer

---

## DATASET

Primary development/evaluation dataset:
**NikolaiSachok/strata-insurance-corpus**

This dataset is used ONLY for:
- Document ingestion testing
- Parsing and OCR testing
- Classification testing
- Information extraction testing
- RAG evaluation
- Golden-question evaluation

The dataset is NOT LLM training data.

---

## ENVIRONMENT AND REPOSITORY

- Workspace: `commercial_submission_ai/`
- Remote: `https://github.com/NaganjaliBiruduraju/commercial_submission_ai.git`
- Branch strategy: `main` for stable code; `feature/*` for active development
- All secrets via environment variables — NEVER committed to Git

---

## PHASE DEVELOPMENT ORDER

1. Project setup and architecture (CURRENT)
2. Authentication and users
3. Document upload
4. PDF/DOCX/XLSX/CSV parsing
5. OCR
6. Document classification
7. Groq LLM integration
8. Structured extraction
9. Evidence mapping
10. Validation
11. Knowledge base
12. Embeddings
13. Vector database
14. RAG
15. Guardrails
16. Risk analysis
17. Underwriter summary
18. Human review workflow
19. Analytics
20. Testing/evaluation
21. Security hardening
22. Production readiness

Each phase must be tested, linted, and committed before proceeding to the next.
