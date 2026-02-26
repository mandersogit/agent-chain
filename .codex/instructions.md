Project: agent-chain — multi-agent chain orchestration CLI (Python, click).

Virtual environment: local.venv/
Test: local.venv/bin/python -m pytest tests/ -v
Lint: local.venv/bin/python -m ruff check src/ tests/
Type check: local.venv/bin/python -m mypy src/agent_chain/

Python 3.11+ required. Use qualified imports (import click as _click).

Do not run any git write commands (commit, add, push, tag, etc.).
