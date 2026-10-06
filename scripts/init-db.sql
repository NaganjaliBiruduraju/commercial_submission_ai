-- Initialize database with pgvector extension
-- This runs automatically when the PostgreSQL container starts

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant permissions
GRANT ALL ON SCHEMA public TO insight_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO insight_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO insight_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO insight_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO insight_user;

-- Verify extension
SELECT * FROM pg_extension WHERE extname = 'vector';
