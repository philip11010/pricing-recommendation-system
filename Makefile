.PHONY: help setup install lint format test clean api assets migrate

help:
	@echo "Available targets:"
	@echo "  setup    - Create virtual environment and install dev dependencies"
	@echo "  install  - Install dev dependencies into active environment"
	@echo "  lint     - Run ruff and black in check mode"
	@echo "  format   - Auto-format code with black and ruff"
	@echo "  test     - Run test suite with coverage"
	@echo "  assets   - Build app_assets/ from a local training run"
	@echo "  migrate  - Apply database migrations"
	@echo "  api      - Run the pricing API development server"
	@echo "  clean    - Remove caches and build artefacts"

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip
	. .venv/bin/activate && pip install -r requirements-dev.txt
	. .venv/bin/activate && pre-commit install
	@echo ""
	@echo "Environment ready. Activate with: source .venv/bin/activate"

install:
	pip install -r requirements-dev.txt

lint:
	ruff check src tests scripts migrations
	black --check src tests scripts migrations

format:
	black src tests scripts migrations
	ruff check --fix src tests scripts migrations

test:
	pytest tests -v --cov=src --cov-report=term-missing

assets:
	python scripts/prepare_app_assets.py

migrate:
	alembic upgrade head

api:
	uvicorn src.mentor.app:app --reload --port 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
