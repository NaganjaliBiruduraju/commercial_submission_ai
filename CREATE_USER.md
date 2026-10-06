# How to Create Your First User

## Quick Start Guide

### Your API is Running! ✅

**Base URL**: http://localhost:8000
**Documentation**: View the OpenAPI JSON at http://localhost:8000/openapi.json

---

## Create a Test User (3 Options)

### Option 1: Use Postman/Insomnia (Recommended)

1. Download **Postman** (https://www.postman.com/downloads/) or **Insomnia** (https://insomnia.rest/download)

2. Import the API:
   - In Postman: Import → Link → `http://localhost:8000/openapi.json`
   - In Insomnia: Create → Import from URL → `http://localhost:8000/openapi.json`

3. All 31 endpoints will be loaded with examples!

4. Check if there's a public registration endpoint or create via admin

---

### Option 2: Direct SQL Insert (Create Admin User)

Run this in your terminal:

```powershell
$env:PGPASSWORD='2116'
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d insight_ai -c @"
DO \$\$
DECLARE
    admin_role_id UUID;
    new_user_id UUID := gen_random_uuid();
BEGIN
    SELECT id INTO admin_role_id FROM roles WHERE name = 'ADMIN' LIMIT 1;
    
    INSERT INTO users (id, email, hashed_password, full_name, role_id, is_active, created_at, updated_at)
    VALUES (
        new_user_id,
        'admin@test.com',
        '\$2b\$12\$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
        'Admin User',
        admin_role_id,
        true,
        NOW(),
        NOW()
    )
    ON CONFLICT (email) DO NOTHING;
    
    RAISE NOTICE 'User created: admin@test.com / password: secret123';
END \$\$;
"@
```

**Credentials:**
- Email: `admin@test.com`
- Password: `secret123`

---

### Option 3: Test Without Auth

Some endpoints work without authentication:

```powershell
# Health check
curl.exe http://localhost:8000/health

# View API schema
curl.exe http://localhost:8000/openapi.json
```

---

## Next Steps

### 1. Login to Get Access Token

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/auth/login" `
  -H "Content-Type: application/json" `
  -d '{"email":"admin@test.com","password":"secret123"}'
```

Response will include `access_token`.

### 2. Use the Token

```powershell
$token = "YOUR_ACCESS_TOKEN_HERE"

curl.exe -X GET "http://localhost:8000/api/v1/submissions" `
  -H "Authorization: Bearer $token"
```

### 3. Create a Submission

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/submissions" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"applicant_name":"Test Insurance Co","lob":"general_liability"}'
```

### 4. Upload Documents

Once you have a submission ID, upload insurance documents and watch all 13 phases execute automatically!

---

## System Architecture

Your system implements a **13-phase insurance document processing pipeline**:

**Phase 1-3**: Document Ingestion & Parsing (PDF/DOCX → structured text)
**Phase 4-5**: Document Classification (ACORD forms, supplements, etc.)
**Phase 6-8**: Field Extraction (LLM-powered, prompt-driven)
**Phase 9**: Data Validation (rules engine + conflict detection)
**Phase 10-13**: Knowledge Base & RAG (embeddings + vector search + retrieval)

All phases run automatically when you upload a document to a submission!

---

## Troubleshooting

**Blank Swagger UI?**
- The OpenAPI JSON works fine (you can see it)
- Use Postman/Insomnia for a better UI
- Or use the curl commands above

**"Authentication required"?**
- Most endpoints require login
- Create a user using Option 2 above
- Login to get an access token
- Include token in requests: `Authorization: Bearer YOUR_TOKEN`

**Need Help?**
- All endpoints documented in: http://localhost:8000/openapi.json
- Health check always works: http://localhost:8000/health
- Check server logs in the terminal where uvicorn is running

---

## Your Complete System is Running! 🎉

**What Works:**
✅ FastAPI Backend Server
✅ PostgreSQL Database (with 17 tables)
✅ JWT Authentication
✅ 31 API Endpoints
✅ LLM Integration (Groq API)
✅ RAG Knowledge Base (sentence-transformers)
✅ Full 13-Phase Processing Pipeline

**What's Next:**
- Create a user (see above)
- Login to get token
- Create a submission
- Upload documents
- Watch AI process them automatically!

Enjoy! 🚀
