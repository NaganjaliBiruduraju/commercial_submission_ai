# INSIGHT AI — Security and Data Steering File

## SECURITY PRINCIPLES

Every uploaded document is UNTRUSTED content.
Every user input is UNTRUSTED.
All secrets are loaded from environment variables — never from source code.

---

## AUTHENTICATION

- JWT tokens (python-jose, HS256)
- Access token: short-lived (15 minutes configurable)
- Refresh token: longer-lived (7 days configurable)
- Passwords: bcrypt hashed — NEVER stored plaintext
- All sensitive endpoints require valid JWT
- Role checked on every protected endpoint

### Roles and Permissions

| Capability                        | ADMIN | UNDERWRITER | REVIEWER |
|-----------------------------------|-------|-------------|----------|
| Manage users                      | ✓     |             |          |
| Upload knowledge documents        | ✓     |             |          |
| Approve knowledge documents       | ✓     |             |          |
| Manage risk rules                 | ✓     |             |          |
| Create submissions                | ✓     | ✓           |          |
| Upload submission documents       | ✓     | ✓           |          |
| Review submissions                | ✓     | ✓           | ✓        |
| Override AI extractions           | ✓     | ✓           |          |
| Set underwriter decision          | ✓     | ✓           |          |
| View analytics                    | ✓     | ✓           | ✓        |
| View audit log                    | ✓     | ✓           | ✓        |

---

## DATABASE SECURITY

- SQLAlchemy ORM with parameterized queries — no raw SQL string concatenation
- Database credentials via DATABASE_URL environment variable
- No credentials in source code
- Connection pooling with sane limits

---

## WHAT IS NEVER LOGGED

- API keys
- JWT secrets
- Passwords (even hashed)
- Full PII unnecessarily
- Raw uploaded document binary content

## WHAT IS ALWAYS LOGGED

- request_id (UUID per request)
- submission_id
- document_id
- processing_stage
- duration_ms
- status (SUCCESS/FAILURE)
- error_code (no stack trace in production logs sent to user)
- user_id (not username/email in sensitive contexts)

---

## HTTP SECURITY HEADERS

Applied via FastAPI middleware:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (production)
- `Content-Security-Policy` (restrictive defaults)

---

## FILE UPLOAD SECURITY

- Whitelist of allowed MIME types and extensions
- Maximum file size enforced (server-side, not just client-side)
- Files stored with generated UUID filenames — never original user filenames on disk
- Original filename stored in database metadata only
- Files stored outside web root

---

## ENVIRONMENT VARIABLES REQUIRED

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/insight_ai

# Authentication
SECRET_KEY=<generate with: openssl rand -hex 32>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM
GROQ_API_KEY=<provided by user — never generated>
LLM_MODEL=openai/gpt-oss-20b
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4096
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Application
APP_ENV=development
APP_DEBUG=false
UPLOAD_DIR=./data/uploads
MAX_UPLOAD_SIZE_MB=50
MAX_FILES_PER_SUBMISSION=20

# Frontend (build-time only — no secrets)
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

## DATABASE SCHEMA PRINCIPLES

- All tables have: id (UUID), created_at, updated_at
- All user-modifiable records have: created_by (FK to users.id)
- Audit log captures every important state change
- Document versions tracked — no silent overwrites
- Foreign keys enforced
- JSON columns used only where flexible nested structure genuinely needed
- No plaintext secrets in any column

---

## AUDIT LOG ENTRIES

Every important action creates an AuditLog record:
- action (enum: CREATED, UPDATED, DELETED, APPROVED, REJECTED, OVERRIDDEN, etc.)
- entity_type (submission, document, knowledge_doc, user, risk_assessment, etc.)
- entity_id
- actor_id (who did it)
- old_value (JSON, nullable)
- new_value (JSON, nullable)
- reason (text, nullable — underwriter notes)
- ip_address (nullable)
- created_at

This provides full traceability for insurance workflow compliance.
