# agent-chain

Multi-agent chain orchestration CLI. Python-only, click-based. Pre-alpha.

## Development

```bash
# Setup
python3.11 -m venv local.venv
local.venv/bin/pip install -e '.[dev]'

# Commands (all use local.venv by default)
make test          # Run tests
make lint          # Lint with ruff
make typecheck     # mypy + pyright
make format        # Format with ruff
make all           # lint + typecheck + test
```

## Conventions

- **Qualified imports only**: `import click as _click` (external), `import agent_chain.chain as chain` (internal)
- **Modern type hints**: `list[str]`, `X | None` — never `typing.List`, `typing.Optional`
- **Python 3.11+** required
- **Google-style docstrings**

## Testing

- Tests must be honest and non-trivial (no "accepts either outcome" assertions)
- Test names describe: what is tested, condition, expected outcome
- Run: `make test` or `local.venv/bin/python -m pytest tests/ -v`

## Virtual Environment

- Location: `local.venv/`
- Override: `PYTHON_EXE=/path/to/python make test`

## Git Policy

**Do not run any git write commands** (commit, add, push, tag, etc.) without explicit user authorization. Read-only commands (status, log, diff) are fine.

## Design Document

Full design: `workflow/2026-02-25-agent-chain-tool-design.md`
