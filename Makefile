# Paimon Backend Makefile
# Usage: make <target>

.PHONY: help install install-dev test lint format clean run migrate

# Default target
help:
	@echo "Paimon Backend - Available Commands"
	@echo ""
	@echo "Setup:"
	@echo "  install        Install production dependencies"
	@echo "  install-dev    Install development dependencies"
	@echo "  setup          Full development setup"
	@echo ""
	@echo "Development:"
	@echo "  run            Run development server"
	@echo "  test           Run tests"
	@echo "  test-cov       Run tests with coverage"
	@echo "  lint           Run linters"
	@echo "  format         Format code"
	@echo ""
	@echo "Database:"
	@echo "  migrate        Run database migrations"
	@echo "  migrate-create Create new migration"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          Clean build artifacts"
	@echo "  docker-up      Start Docker services"
	@echo "  docker-down    Stop Docker services"

# Installation
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
	pre-commit install

setup: install-dev
	cp -n .env.example .env || true
	@echo "Setup complete! Edit .env with your configuration."

# Development
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-prod:
	gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Testing
test:
	PYTHONPATH=src pytest tests/ -v

test-cov:
	PYTHONPATH=src pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

test-unit:
	PYTHONPATH=src pytest tests/unit/ -v

test-integration:
	PYTHONPATH=src pytest tests/integration/ -v

# Code Quality
lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check src/ tests/ --fix

# Database
migrate:
	alembic upgrade head

migrate-create:
	@read -p "Migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

migrate-rollback:
	alembic downgrade -1

# Docker
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Maintenance
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# Pre-commit
pre-commit:
	pre-commit run --all-files

pre-commit-update:
	pre-commit autoupdate
