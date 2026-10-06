.PHONY: help install dev test lint format clean docker-up docker-down docker-logs migrate

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python dependencies
	pip install -r requirements.txt

dev: ## Run development server
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run tests
	cd backend && pytest -v

test-cov: ## Run tests with coverage
	cd backend && pytest --cov=app --cov-report=html --cov-report=term

lint: ## Run linters
	ruff check backend/app
	black --check backend/app
	mypy backend/app --ignore-missing-imports

format: ## Format code
	black backend/app
	ruff check --fix backend/app

clean: ## Clean up temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf backend/htmlcov/

docker-up: ## Start Docker containers
	docker-compose up -d

docker-down: ## Stop Docker containers
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-build: ## Build Docker images
	docker-compose build

docker-clean: ## Remove Docker containers and volumes
	docker-compose down -v

migrate: ## Run database migrations
	cd backend && alembic upgrade head

migrate-create: ## Create a new migration (use MSG="migration message")
	cd backend && alembic revision --autogenerate -m "$(MSG)"

migrate-downgrade: ## Downgrade database by one revision
	cd backend && alembic downgrade -1

db-reset: ## Reset database (WARNING: destroys all data)
	cd backend && alembic downgrade base && alembic upgrade head

seed: ## Seed database with sample data
	cd backend && python scripts/seed_data.py

backup: ## Backup database
	docker exec insight_ai_postgres pg_dump -U insight_user insight_ai > backup_$$(date +%Y%m%d_%H%M%S).sql

restore: ## Restore database from backup (use FILE=backup.sql)
	docker exec -i insight_ai_postgres psql -U insight_user insight_ai < $(FILE)

logs: ## View application logs
	tail -f backend/logs/app.log

healthcheck: ## Check if services are running
	@echo "Checking backend..."
	@curl -f http://localhost:8000/health || echo "Backend not running"
	@echo "\nChecking database..."
	@docker exec insight_ai_postgres pg_isready -U insight_user || echo "Database not running"
	@echo "\nChecking Redis..."
	@docker exec insight_ai_redis redis-cli ping || echo "Redis not running"
