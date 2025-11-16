.PHONY: help install dev test lint format clean docker-build docker-up deploy

# Default target
help:
	@echo "DevFlowFix - Available Commands:"
	@echo "  make install       - Install dependencies with uv"
	@echo "  make dev           - Start development server"
	@echo "  make test          - Run tests"
	@echo "  make test-cov      - Run tests with coverage report"
	@echo "  make lint          - Run linters (ruff, mypy)"
	@echo "  make format        - Format code (black, isort, ruff)"
	@echo "  make clean         - Clean cache and build files"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-up     - Start Docker Compose stack"
	@echo "  make docker-down   - Stop Docker Compose stack"
	@echo "  make migrate       - Run database migrations"
	@echo "  make deploy-dev    - Deploy to dev environment"

install:
	@echo "Installing dependencies with uv..."
	uv sync

dev:
	@echo "Starting development server..."
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	@echo "Running tests..."
	uv run pytest

test-cov:
	@echo "Running tests with coverage..."
	uv run pytest --cov=app --cov-report=html --cov-report=term

lint:
	@echo "Running linters..."
	uv run ruff check app tests
	uv run mypy app

format:
	@echo "Formatting code..."
	uv run ruff format app tests
	uv run isort app tests

clean:
	@echo "Cleaning cache and build files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf htmlcov/ .coverage

docker-build:
	@echo "Building Docker image..."
	docker build -f Dockerfile.lambda -t devflowfix:latest .

docker-up:
	@echo "Starting Docker Compose stack..."
	docker-compose up -d
	@echo "Services running at:"
	@echo "  - PostgreSQL: localhost:5432"
	@echo "  - App: localhost:8000"

docker-down:
	@echo "Stopping Docker Compose stack..."
	docker-compose down

migrate:
	@echo "Running database migrations..."
	uv run alembic upgrade head

migrate-create:
	@echo "Creating new migration..."
	@read -p "Migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"

deploy-dev:
	@echo "Deploying to dev environment..."
	./scripts/deploy_lambda.sh dev

deploy-staging:
	@echo "Deploying to staging environment..."
	./scripts/deploy_lambda.sh staging

deploy-prod:
	@echo "Deploying to production environment..."
	@read -p "Are you sure you want to deploy to PRODUCTION? [y/N]: " confirm; \
	if [ "$$confirm" = "y" ]; then \
		./scripts/deploy_lambda.sh prod; \
	else \
		echo "Deployment cancelled."; \
	fi
