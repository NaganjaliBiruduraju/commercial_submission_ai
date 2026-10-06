# Commercial Submission AI

> AI-powered insurance document intelligence and underwriting support system

## Overview

A comprehensive, production-ready platform that processes commercial insurance submissions through a 13-phase AI pipeline:

- **Document Ingestion & Parsing**: PDF, DOCX, XLSX, images
- **OCR & Classification**: Tesseract OCR + LLM-powered document type detection
- **AI Extraction**: Prompt-driven field extraction with Groq LLM
- **Data Validation**: 15+ validation rules + conflict detection
- **Knowledge Base & RAG**: Semantic search over underwriting guidelines

## Features

✅ **13-Phase Processing Pipeline**
- Automated document parsing, classification, extraction, and validation
- All phases execute automatically on document upload

✅ **Prompt-Driven Architecture**
- Output structure controlled 100% by prompts
- No fixed schemas - fully flexible extraction

✅ **RAG-Enhanced Extraction**
- Local embeddings (sentence-transformers)
- Vector similarity search with pgvector
- Context-aware field extraction

✅ **Production-Ready**
- Docker Compose setup
- PostgreSQL with pgvector
- JWT authentication
- Async/await throughout
- Structured logging

✅ **API-First Design**
- 31 REST endpoints
- OpenAPI/Swagger documentation
- Full CRUD operations

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- PostgreSQL 16+ with pgvector (or use Docker)

### Using Docker (Recommended)

```bash
# Clone repository
git clone <repo-url>
cd commercial_submission_ai

# Copy environment file
cp .env.docker .env
# Edit .env and add your GROQ_API_KEY

# Start all services (includes pgvector!)
docker-compose up -d

# Check health
curl http://localhost:8000/health

# View logs
docker-compose logs -f backend
```

**Services started:**
- Backend API: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
createdb insight_ai
psql -d insight_ai -c "CREATE EXTENSION vector;"

# Copy environment file
cp backend/.env.example backend/.env
# Edit backend/.env with your settings

# Run migrations
cd backend
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

## API Documentation

Once running, access interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Testing

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
cd backend
pytest tests/test_health.py -v
```

## Project Structure

```
commercial_submission_ai/
├── backend/
│   ├── app/
│   │   ├── ai/              # LLM integration (Groq)
│   │   ├── api/             # REST API routes
│   │   ├── auth/            # JWT authentication
│   │   ├── classification/  # Document classification
│   │   ├── core/            # Config, logging, constants
│   │   ├── database/        # Database setup & migrations
│   │   ├── extraction/      # Prompt-driven field extraction
│   │   ├── ingestion/       # Document parsing (PDF/DOCX/OCR)
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── rag/             # Embeddings + vector search
│   │   ├── repositories/    # Data access layer
│   │   ├── schemas/         # Pydantic models
│   │   ├── services/        # Business logic
│   │   ├── utils/           # Utilities
│   │   └── validation/      # Validation rules engine
│   ├── alembic/             # Database migrations
│   ├── tests/               # Test suite
│   └── pytest.ini
├── data/
│   ├── uploads/             # User-uploaded documents
│   ├── knowledge/           # Underwriting guidelines
│   └── raw/strata_insurance_corpus/  # Sample data
├── scripts/                 # Utility scripts
├── .github/workflows/       # CI/CD pipelines
├── docker-compose.yml       # Docker orchestration
├── Dockerfile               # Backend container
├── Makefile                 # Development commands
└── requirements.txt         # Python dependencies
```

## Architecture

### Data Flow

```
1. Upload Document
   ↓
2. Parse (PDF/DOCX → text)
   ↓
3. Classify (determine document type)
   ↓
4. Extract (LLM extracts fields via prompt)
   ↓
5. Validate (rules engine checks data)
   ↓
6. Store (PostgreSQL)
   ↓
7. Return Results (API response)
```

### RAG Pipeline

```
1. Admin uploads guideline document
   ↓
2. Chunk text (400 words, 40-word overlap)
   ↓
3. Generate embeddings (sentence-transformers)
   ↓
4. Store vectors (PostgreSQL + pgvector)
   ↓
5. Query → Embed → Search → Retrieve context
   ↓
6. Inject context into extraction prompt
```

## Configuration

Key environment variables (see `.env.example`):

```bash
# LLM
GROQ_API_KEY=your_key_here
LLM_MODEL=openai/gpt-oss-20b

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db

# Auth
SECRET_KEY=generate_with_openssl_rand_hex_32
ACCESS_TOKEN_EXPIRE_MINUTES=15

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
```

## Deployment

### Production with Docker

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head

# Check logs
docker-compose logs -f
```

### Environment-Specific

Create environment-specific compose files:

- `docker-compose.yml` - base config
- `docker-compose.prod.yml` - production overrides
- `docker-compose.dev.yml` - development overrides

```bash
# Production deployment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Makefile Commands

```bash
make help           # Show all available commands
make dev            # Start development server
make test           # Run tests
make test-cov       # Run tests with coverage
make lint           # Run linters
make format         # Format code
make docker-up      # Start Docker services
make docker-logs    # View Docker logs
make migrate        # Run database migrations
make clean          # Clean temporary files
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Login and get JWT
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user

### Submissions
- `POST /api/v1/submissions` - Create submission
- `GET /api/v1/submissions` - List submissions
- `GET /api/v1/submissions/{id}` - Get submission
- `POST /api/v1/submissions/{id}/documents` - Upload document
- `POST /api/v1/submissions/{id}/process` - Trigger processing

### Knowledge Base (Admin)
- `POST /api/v1/knowledge/upload` - Upload guideline
- `POST /api/v1/knowledge/{id}/approve` - Approve & index
- `POST /api/v1/knowledge/rebuild-index` - Rebuild vector index
- `POST /api/v1/knowledge/search` - Test RAG retrieval

## Testing with Sample Data

The project includes the Strata Insurance Corpus with 79 synthetic documents:

```bash
# View sample documents
ls data/raw/strata_insurance_corpus/sample/docs/

# Policy declarations, contracts, endorsements
# Claim FNOL, adjuster reports, settlements
# Identity cards with PII
# Knowledge base (guidelines, manuals, FAQs)
# Tabular data (loss runs, premium registers)
```

## Troubleshooting

### pgvector not found

If using local PostgreSQL instead of Docker:

```bash
# Install pgvector extension
# Follow: https://github.com/pgvector/pgvector#installation

# Then in psql:
CREATE EXTENSION vector;
```

### Swagger UI blank screen

- Try ReDoc: http://localhost:8000/redoc
- Check browser console for CDN blocks
- Use Postman and import OpenAPI JSON

### Tests failing

```bash
# Create test database
createdb insight_ai_test
psql -d insight_ai_test -c "CREATE EXTENSION vector;"

# Set test environment
export DATABASE_URL=postgresql+asyncpg://user:pass@localhost/insight_ai_test
export APP_ENV=testing
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Run tests: `make test`
4. Run linters: `make lint`
5. Format code: `make format`
6. Submit a pull request

## License

[Add your license here]

## Support

For issues and questions, please open a GitHub issue.
