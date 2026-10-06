# Quick Start Guide

Get the Commercial Insurance AI system running in 5 minutes.

## Prerequisites

- Docker Desktop installed and running
- Git installed
- 8GB RAM minimum

## Option 1: Docker Compose (Recommended)

### 1. Clone & Setup

```bash
git clone https://github.com/NaganjaliBiruduraju/commercial_submission_ai.git
cd commercial_submission_ai
```

### 2. Configure Environment

```bash
# Copy environment file
cp .env.docker .env

# Edit .env and add your Groq API key
# GROQ_API_KEY=gsk_YOUR_KEY_HERE
```

### 3. Start All Services

```bash
# Start backend + database + Redis
docker-compose up -d

# Wait 30 seconds for database initialization

# Check health
curl http://localhost:8000/health
```

### 4. Access the Application

- **Backend API**: http://localhost:8000/docs
- **Backend Health**: http://localhost:8000/health

### 5. (Optional) Start Frontend

```bash
# Start frontend in Docker
docker-compose up -d frontend
```

- **Frontend UI**: http://localhost:3000

## Option 2: Local Development

### Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up database
createdb insight_ai
psql -d insight_ai -c "CREATE EXTENSION vector;"

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env

# Start development server
npm run dev
```

## First Steps

### 1. Create an Account

**Via UI** (if frontend is running):
- Navigate to http://localhost:5173 (dev) or http://localhost:3000 (Docker)
- Click "Register" tab
- Fill in email, password, full name
- Click "Sign Up"

**Via API**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "SecurePass123!",
    "full_name": "Admin User"
  }'
```

### 2. Login

**Via UI**:
- Use the Login tab with your credentials

**Via API**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: multipart/form-data" \
  -F "username=admin@example.com" \
  -F "password=SecurePass123!"
```

Save the `access_token` from the response.

### 3. Create a Submission

**Via UI**:
1. Click "Submissions" in navigation
2. Click "Create New Submission"
3. Enter submission details
4. Upload documents (PDF, DOCX)
5. Click "Process Submission"

**Via API**:
```bash
# Create submission
TOKEN="your_access_token_here"

curl -X POST "http://localhost:8000/api/v1/submissions/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "submission_name": "Test Submission",
    "insured_name": "ABC Corp",
    "broker_name": "XYZ Brokers"
  }'

# Upload document
SUBMISSION_ID="submission_id_from_previous_response"

curl -X POST "http://localhost:8000/api/v1/submissions/$SUBMISSION_ID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/document.pdf"

# Process submission
curl -X POST "http://localhost:8000/api/v1/submissions/$SUBMISSION_ID/process" \
  -H "Authorization: Bearer $TOKEN"
```

### 4. View Results

**Via UI**:
1. Click on the submission card
2. Navigate through tabs:
   - **Documents**: See uploaded files
   - **Extracted**: View extracted data
   - **Validation**: Check validation results
   - **Risk**: See risk assessment

**Via API**:
```bash
# Get extracted data
curl -X GET "http://localhost:8000/api/v1/submissions/$SUBMISSION_ID/extracted" \
  -H "Authorization: Bearer $TOKEN"

# Get validation results
curl -X GET "http://localhost:8000/api/v1/submissions/$SUBMISSION_ID/validation" \
  -H "Authorization: Bearer $TOKEN"

# Get risk assessment
curl -X GET "http://localhost:8000/api/v1/submissions/$SUBMISSION_ID/risk" \
  -H "Authorization: Bearer $TOKEN"
```

## Knowledge Base

### Add Articles

**Via UI**:
1. Click "Knowledge Base" in navigation
2. Click "Create Article"
3. Fill in title, content, category, tags
4. Click "Create Article"

**Via API**:
```bash
curl -X POST "http://localhost:8000/api/v1/knowledge/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Property Insurance Guidelines",
    "content": "Detailed guidelines for property insurance...",
    "category": "Guidelines",
    "tags": ["property", "guidelines"]
  }'
```

### Search Knowledge Base

**Via UI**:
1. Enter natural language query in search box
2. Click "Search"
3. View results with similarity scores

**Via API**:
```bash
curl -X POST "http://localhost:8000/api/v1/knowledge/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the requirements for property insurance?",
    "top_k": 5
  }'
```

## Troubleshooting

### Backend Won't Start

```bash
# Check Docker logs
docker-compose logs backend

# Common issues:
# 1. Database not ready - wait 30 seconds after starting
# 2. Missing GROQ_API_KEY - check .env file
# 3. Port 8000 in use - stop other services or change port
```

### Frontend Won't Start

```bash
# Check if dependencies are installed
cd frontend
npm install

# Check if backend is running
curl http://localhost:8000/health

# Check .env configuration
cat .env
```

### Database Issues

```bash
# Reset database
docker-compose down -v
docker-compose up -d postgres

# Wait 30 seconds, then start backend
docker-compose up -d backend
```

### API Errors

```bash
# Check if you're authenticated
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me

# Token expired? Login again to get new token
```

## Useful Commands

### Docker

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend

# Restart a service
docker-compose restart backend

# Stop all services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v
```

### Database

```bash
# Access PostgreSQL
docker-compose exec postgres psql -U insight_user -d insight_ai

# List tables
\dt

# View schema
\d+ submissions
```

### Backend

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Create new migration
docker-compose exec backend alembic revision --autogenerate -m "description"

# Access backend shell
docker-compose exec backend /bin/bash
```

## What's Running?

After `docker-compose up -d`:

| Service | Port | URL |
|---------|------|-----|
| Backend API | 8000 | http://localhost:8000 |
| Frontend | 3000 | http://localhost:3000 |
| PostgreSQL | 5432 | localhost:5432 |
| Redis | 6379 | localhost:6379 |
| API Docs | 8000 | http://localhost:8000/docs |
| ReDoc | 8000 | http://localhost:8000/redoc |

## Next Steps

1. **Explore the UI**: Navigate through all pages to see features
2. **Test API**: Use Swagger UI at http://localhost:8000/docs
3. **Upload Documents**: Try different document types (PDF, DOCX)
4. **Search Knowledge**: Add articles and test semantic search
5. **Check Logs**: Monitor processing in docker logs

## Support

- **Documentation**: See README.md and frontend/README.md
- **API Reference**: http://localhost:8000/docs
- **Architecture**: See PRODUCTION_READY.md
- **Frontend Guide**: See FRONTEND_COMPLETE.md

## Production Deployment

For production deployment, see:
- DEPLOYMENT.md - Detailed deployment guide
- PRODUCTION_READY.md - Production checklist
- docker-compose.yml - Service configuration

---

**You're all set! Start processing insurance documents with AI. 🚀**
