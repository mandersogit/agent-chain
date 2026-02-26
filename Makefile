# agent-chain development Makefile
#
# Set PYTHON_EXE to override the Python interpreter (defaults to local.venv).

PYTHON_EXE ?= $(CURDIR)/local.venv/bin/python

.PHONY: test test-cov lint typecheck typecheck-mypy typecheck-pyright format all clean install help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Run all tests
	$(PYTHON_EXE) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTHON_EXE) -m pytest tests/ -v \
		--cov=agent_chain \
		--cov-report=term-missing \
		--cov-report=html:coverage_html

lint: ## Lint with ruff
	$(PYTHON_EXE) -m ruff check src/ tests/

typecheck: typecheck-mypy typecheck-pyright ## Run mypy and pyright type checkers

typecheck-mypy: ## Type-check with mypy
	$(PYTHON_EXE) -m mypy src/agent_chain/

typecheck-pyright: ## Type-check with pyright
	$(PYTHON_EXE) -m pyright src/agent_chain/

format: ## Format code with ruff
	$(PYTHON_EXE) -m ruff check src/ tests/ --fix
	$(PYTHON_EXE) -m ruff format src/ tests/

all: lint typecheck test ## Run lint, typecheck, and tests

clean: ## Remove build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .pyright/
	rm -rf .ruff_cache/
	rm -rf coverage_html/
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

install: ## Install editable + dev deps into local.venv
	$(PYTHON_EXE) -m pip install -e '.[dev]'
