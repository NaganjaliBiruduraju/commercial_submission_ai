# Deployment Guide

## Quick Start with Docker (Recommended)

### Step 1: Prerequisites

```bash
# Install Docker Desktop (Windows/Mac)
# OR Docker Engine + Docker Compose (Linux)

# Verify installation
docker --version
docker-compose --version
```

### Step 2: Clone and Configure

```bash
# Clone repository
git clone <your-repo-url>
cd commercial_submission_ai

# Copy environment template
cp .env.docker .env

# Edit .env and set your GROQ_API_KEY
nano .env  # or use any text editor
```

### Step 3: Start Services

```bash
# Start everything (backend + PostgreSQL with pgvector + Redis)
docker-compose up -d

# Wait for services to be ready (~30 seconds)
docker-compose logs -f backend

# When you see "Application startup complete", press Ctrl+C
```

### Step 4: Verify

```bash
# Check health
curl http://localhost:8000/health

# Expected response:
# {"success":true,"data":{"status":"ok","version":"1.0.0",...}}

# Access API docs
open http://localhost:8000/docs  # Mac
start http://localhost:8000/docs # Windows
```

**🎉 Done! Your system is running with pgvector enabled.**

---

## Production Deployment

### Option 1: Docker on VM/EC2

```bash
# On your production server

# 1. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Clone repository
git clone <your-repo-url>
cd commercial_submission_ai

# 3. Create production .env
cp .env.docker .env.production
nano .env.production

# Set production values:
# - Strong SECRET_KEY (openssl rand -hex 32)
# - Production DATABASE_URL if using external DB
# - APP_ENV=production
# - Restrict CORS_ORIGINS

# 4. Start with production config
docker-compose --env-file .env.production up -d

# 5. Set up SSL/TLS (use nginx or Traefik)
```

### Option 2: Kubernetes (Advanced)

```bash
# Coming soon: kubectl manifests for K8s deployment
```

### Option 3: Cloud-Specific

#### AWS (Elastic Beanstalk)

```bash
# 1. Install EB CLI
pip install awsebcli

# 2. Initialize
eb init -p docker commercial-submission-ai

# 3. Create environment
eb create production

# 4. Deploy
eb deploy

# 5. Set environment variables
eb setenv GROQ_API_KEY=your_key DATABASE_URL=your_db_url
```

#### Google Cloud Run

```bash
# 1. Build image
gcloud builds submit --tag gcr.io/YOUR_PROJECT/commercial-submission-ai

# 2. Deploy
gcloud run deploy commercial-submission-ai \
  --image gcr.io/YOUR_PROJECT/commercial-submission-ai \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GROQ_API_KEY=your_key

# 3. Connect Cloud SQL (PostgreSQL with pgvector)
gcloud run services update commercial-submission-ai \
  --add-cloudsql-instances YOUR_PROJECT:us-central1:your-db
```

---

## pgvector Installation

### If Using Docker (Automatic)

pgvector is included in the `pgvector/pgvector:pg16` image. No manual installation needed!

### If Using Local PostgreSQL

#### Linux (Ubuntu/Debian)

```bash
# Install build tools
sudo apt install postgresql-server-dev-16 build-essential

# Clone and build pgvector
cd /tmp
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# Enable in your database
psql -U postgres -d insight_ai -c "CREATE EXTENSION vector;"
```

#### macOS (Homebrew)

```bash
# Install pgvector via Homebrew
brew install pgvector

# Restart PostgreSQL
brew services restart postgresql@16

# Enable extension
psql -U postgres -d insight_ai -c "CREATE EXTENSION vector;"
```

#### Windows

pgvector on Windows PostgreSQL is complex. **Recommended: Use Docker instead.**

If you must use local PostgreSQL:
1. Use WSL2 with Docker
2. OR compile from source (requires Visual Studio)
3. OR use the Docker container just for PostgreSQL:

```powershell
# Run only PostgreSQL with pgvector
docker run -d \
  --name insight_postgres \
  -e POSTGRES_USER=insight_user \
  -e POSTGRES_PASSWORD=insight_pass \
  -e POSTGRES_DB=insight_ai \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Update your .env to point to localhost:5432
```

---

## Environment Variables

### Required

```bash
GROQ_API_KEY=gsk_...           # Get from https://console.groq.com/
SECRET_KEY=<random_hex_32>     # Generate: openssl rand -hex 32
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname
```

### Optional (with defaults)

```bash
APP_ENV=production             # development, testing, production
APP_DEBUG=false                # Set true for dev only
CORS_ORIGINS=https://your-frontend.com
LLM_MODEL=openai/gpt-oss-20b
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
LOG_LEVEL=INFO
MAX_UPLOAD_SIZE_MB=50
```

---

## Database Setup

### Automated (with Docker)

The `init-db.sql` script runs automatically and creates the pgvector extension.

### Manual

```bash
# 1. Create database
createdb insight_ai

# 2. Enable pgvector
psql -d insight_ai -c "CREATE EXTENSION vector;"

# 3. Run migrations
cd backend
alembic upgrade head

# 4. (Optional) Seed data
python scripts/seed_data.py
```

---

## SSL/TLS Configuration

### With Nginx (Recommended)

```nginx
# /etc/nginx/sites-available/commercial-submission-ai

server {
    listen 80;
    server_name api.yourcompany.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/api.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourcompany.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### With Traefik (Docker)

```yaml
# docker-compose.prod.yml

services:
  backend:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.backend.rule=Host(`api.yourcompany.com`)"
      - "traefik.http.routers.backend.entrypoints=websecure"
      - "traefik.http.routers.backend.tls.certresolver=letsencrypt"
```

---

## Monitoring

### Health Checks

```bash
# Endpoint
curl https://api.yourcompany.com/health

# Expected response time: <200ms
# Monitor: status, database, llm_configured
```

### Logging

```bash
# View logs
docker-compose logs -f backend

# Or if deployed to cloud, use their logging:
# AWS CloudWatch, GCP Cloud Logging, Azure Monitor
```

### Metrics (Future)

```bash
# Coming soon: Prometheus + Grafana integration
# Metrics: request rate, latency, error rate, LLM usage
```

---

## Backup & Recovery

### Database Backup

```bash
# Automated backup (cron job)
0 2 * * * docker exec insight_ai_postgres pg_dump -U insight_user insight_ai | gzip > /backups/insight_ai_$(date +\%Y\%m\%d).sql.gz

# Manual backup
docker exec insight_ai_postgres pg_dump -U insight_user insight_ai > backup.sql

# Restore
docker exec -i insight_ai_postgres psql -U insight_user insight_ai < backup.sql
```

### File Storage Backup

```bash
# Backup uploads and knowledge documents
tar -czf data_backup_$(date +%Y%m%d).tar.gz data/uploads data/knowledge

# Restore
tar -xzf data_backup_20240101.tar.gz
```

---

## Scaling

### Horizontal Scaling

```yaml
# docker-compose.prod.yml

services:
  backend:
    deploy:
      replicas: 3  # Run 3 instances
    
  nginx:
    # Add load balancer
```

### Caching with Redis

```python
# Already configured in docker-compose.yml
# Use for:
# - Rate limiting
# - Session storage
# - Caching embeddings
```

---

## Security Checklist

- [ ] Strong SECRET_KEY (32+ bytes)
- [ ] HTTPS/TLS enabled
- [ ] CORS properly configured
- [ ] Database credentials secured
- [ ] GROQ_API_KEY in environment, not code
- [ ] Rate limiting enabled
- [ ] Input validation active
- [ ] File upload size limits enforced
- [ ] Regular security updates
- [ ] Audit logs enabled

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs backend

# Common issues:
# - Missing GROQ_API_KEY
# - Database connection failed
# - Port 8000 already in use
```

### pgvector errors

```bash
# Verify extension installed
docker exec insight_ai_postgres psql -U insight_user -d insight_ai -c "\dx vector"

# If not found, rebuild container:
docker-compose down -v
docker-compose up -d
```

### High memory usage

```bash
# Limit container resources in docker-compose.yml:
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
```

---

## Support

For deployment issues:
1. Check logs: `docker-compose logs -f`
2. Review [README.md](README.md)
3. Open GitHub issue with logs
