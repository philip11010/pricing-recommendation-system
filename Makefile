.PHONY: help setup install lint format test clean api assets migrate \n	web-install web-dev web-build web-lint web-test web-e2e

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
	@echo ""
	@echo "  web-install - Install the web application's dependencies"
	@echo "  web-dev     - Run the mentor-facing web application on :3000"
	@echo "  web-build   - Production build of the web application"
	@echo "  web-lint    - Lint and type check the web application"
	@echo "  web-test    - Unit tests for the web application"
	@echo "  web-e2e     - End-to-end tests (the API has to be running)"
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

# The mentor-facing web application. It has no backend of its own: it calls
# the pricing API from the browser, so `make api` has to be running too, and
# web-e2e needs the demonstration mentors seeded as well. See web/README.md.
web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

web-lint:
	cd web && npm run lint && npm run typecheck

web-test:
	cd web && npm run test

web-e2e:
	cd web && npm run e2e
