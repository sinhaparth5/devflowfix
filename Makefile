.PHONY: help install dev test test-cov lint format clean docker-build docker-up docker-down migrate migrate-create deploy-dev deploy-staging deploy-prod ruff-check ruff-format pre-commit-install pre-commit-run

# Default target
help:
	@echo "DevFlowFix - Available Commands:"
	@echo "  make install       - Install dependencies with uv"
	@echo "  make dev           - Start development server"
	@echo "  make test          - Run tests"
	@echo "  make test-cov      - Run tests with coverage report"
	@echo "  make lint          - Run linters (ruff, mypy)"
	@echo "  make format        - Format code (ruff)"
	@echo "  make ruff-check    - Run Ruff lint checks"
	@echo "  make ruff-format   - Run Ruff formatter"
	@echo "  make pre-commit-install - Install pre-commit hooks"
	@echo "  make pre-commit-run - Run pre-commit on all files"
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

ruff-check:
	@echo "Running Ruff checks..."
	uv run ruff check app tests

ruff-format:
	@echo "Running Ruff formatter..."
	uv run ruff format app tests

pre-commit-install:
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install

pre-commit-run:
	@echo "Running pre-commit on all files..."
	uv run pre-commit run --all-files

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
	docker compose -f infrastructure/docker/compose.yml up --build --remove-orphans
	@echo "Services running at:"
	@echo "  - PostgreSQL: localhost:5433"
	@echo "  - App: localhost:8001"
	@echo "  - ngrok dashboard: localhost:4040"

docker-down:
	@echo "Stopping Docker Compose stack..."
	docker compose -f infrastructure/docker/compose.yml down

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
