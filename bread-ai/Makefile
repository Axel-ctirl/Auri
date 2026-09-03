# Bread developer shortcuts.
#
# Windows users: these need GNU make. Everything here is a one-line command you
# can also run directly; see the README.

.DEFAULT_GOAL := help
.PHONY: help install install-dev install-inference install-train serve dev \
        frontend build test test-backend test-frontend lint format typecheck \
        check status clean clean-data

PYTHON ?= python

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install the backend (no PyTorch)
	$(PYTHON) -m pip install -r requirements.txt

install-dev:  ## Install backend plus lint, type and test tooling
	$(PYTHON) -m pip install -r requirements-dev.txt

install-inference:  ## Install Transformers inference (install torch first)
	$(PYTHON) -m pip install -r requirements-inference.txt

install-train:  ## Install the fine-tuning stack (install torch first)
	$(PYTHON) -m pip install -r requirements-train.txt

serve:  ## Run the API on 127.0.0.1:8000
	cd backend && $(PYTHON) -m app.cli serve

dev:  ## Run the API with auto-reload
	cd backend && $(PYTHON) -m app.cli serve --reload

frontend:  ## Run the Vite dev server on 127.0.0.1:5173
	cd frontend && npm run dev

build:  ## Build the frontend into frontend/dist
	cd frontend && npm run build

test: test-backend test-frontend  ## Run every test

test-backend:  ## Run the Python test suite
	$(PYTHON) -m pytest

test-frontend:  ## Run the frontend test suite
	cd frontend && npm test

lint:  ## Lint the Python source
	ruff check .

format:  ## Format the Python source
	black .
	ruff check . --fix

typecheck:  ## Type-check both halves
	$(PYTHON) -m mypy
	cd frontend && npm run typecheck

check: lint typecheck test  ## Everything CI runs

status:  ## Print GPU, dependency and configuration status
	cd backend && $(PYTHON) -m app.cli status

clean:  ## Remove build artefacts and caches
	rm -rf frontend/dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

clean-data:  ## Delete every local database, index and upload. Irreversible.
	@echo "This deletes data/ : conversations, documents, vectors, datasets and runs."
	@read -p "Type yes to continue: " answer; [ "$$answer" = "yes" ] || exit 1
	rm -rf data/bread.db data/bread.db-wal data/bread.db-shm \
	       data/uploads data/vectors data/datasets data/runs
