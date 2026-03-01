# agent-chain
Multi-agent chain orchestration CLI for reproducible implementation, review, fix, and verification pipelines.

## Overview
`agent-chain` runs a sequence of steps from a TOML chain file. Each step can invoke an agent backend (`codex-cli`, `claude-code`, or `cursor-cli`) or run a verification gate only (`agent = "none"`).

Why it exists:
- Make multi-step agent workflows repeatable and auditable.
- Mix agent CLIs in one pipeline.
- Add deterministic shell gates between agent steps.
- Persist outputs, telemetry, and a machine-readable `report.json`.

Each run writes:
- `steps/<step-name>/...` artifacts per step
- `report.json` with chain/step outcomes and totals
- `DONE` sentinel containing final chain status

## Installation
Requirements:
- Python `3.11+`
- Optional backend CLIs (depending on your chain):
  - `codex` for `codex-cli` steps
  - `claude` for `claude-code` steps
  - `cursor-agent` for `cursor-cli` steps

### Install from source
```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Verify installation:
```bash
agent-chain --help
```

## Quick Start
Create `quickstart.toml`:

```toml
[chain]
name = "quickstart"
description = "Implement then verify"
default_timeout = 1800

[vars]
task = "Add a short project summary to README.md"

[[steps]]
name = "implement"
type = "implement"
agent = "codex-cli"

[steps.brief]
source = "inline"
text = "{{task}}"

[steps.agent_config]
sandbox = "full-auto"
reasoning_effort = "high"

[[steps]]
name = "verify"
type = "verify"
agent = "none"

[steps.gate]
command = "test -f README.md"
expected_exit_code = 0
```

Run it:

```bash
agent-chain validate quickstart.toml
agent-chain run -v -o .agent-chain/quickstart quickstart.toml
agent-chain report .agent-chain/quickstart
```

## Chain Definition Format
A chain file is TOML with:
- `[chain]` for metadata/defaults
- `[vars]` for user template variables
- `[[steps]]` for ordered execution steps

### Full skeleton
```toml
[chain]
name = "my-chain"
description = "Example"
default_timeout = 1800
working_dir = "."

[vars]
project_root = "."

[[steps]]
name = "implement"
type = "implement"
agent = "codex-cli"

[steps.brief]
source = "inline"
text = "Implement in {{project_root}}"
# path = "briefs/implement.md" # when source = "file"

[steps.agent_config]
sandbox = "full-auto"
reasoning_effort = "high"
model = "sonnet"
effort = "high"
permission_mode = "dangerously-skip-permissions"
max_turns = 50
timeout = 1200
output_schema = "schemas/result.schema.json"
extra_flags = ["--flag"]

[steps.gate]
command = "pytest -q"
expected_exit_code = 0
on_failure = "abort"
```

### `[chain]` fields
| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `name` | `string` | Yes | - | Non-empty chain name. |
| `description` | `string` | No | `""` | Human-readable description. |
| `default_timeout` | `int` | No | `1800` | Default step timeout in seconds. |
| `working_dir` | `string` | No | Chain file directory | Working directory for agent and gate commands. |

### `[vars]` fields
| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `<any key>` | Any TOML scalar | No | - | Converted to string and exposed as `{{key}}`. |

### `[[steps]]` fields
| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `name` | `string` | Yes | - | Unique step name. |
| `type` | `string` | Yes | - | `implement`, `review`, `fix`, `verify`, `custom`. |
| `agent` | `string` | Yes | - | `codex-cli`, `claude-code`, `cursor-cli`, or `none`. |
| `brief` | table | Conditional | - | Required for non-`verify` when `agent != "none"`. |
| `agent_config` | table | No | `{}` | Backend-specific options. |
| `gate` | table | Conditional | - | Required for `verify`; optional otherwise. |

### `[steps.brief]` fields
| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `source` | `string` | No | `"inline"` | `inline` or `file`. |
| `text` | `string` | If `source = "inline"` | `""` | Inline brief text with template variables. |
| `path` | `string` | If `source = "file"` | `""` | Brief file path; relative paths resolve from chain file dir. |

### `[steps.gate]` fields
| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `command` | `string` | No | `""` | Shell command run after successful step execution. |
| `expected_exit_code` | `int` | No | `0` | Gate passes only when exit code matches. |
| `on_failure` | `string` | No | `"abort"` | `abort`, `warn`, or `skip`. |
| `timeout` | `int` | No | `300` | Gate command timeout in seconds. `0` means no limit. |

### `[steps.agent_config]` fields
| Field | Type | Applies to | Default | Notes |
| --- | --- | --- | --- | --- |
| `sandbox` | `string` | `codex-cli` | `"full-auto"` | `"read-only"` maps to `--sandbox read-only`; anything else maps to `--full-auto`. |
| `reasoning_effort` | `string` | `codex-cli` | `"medium"` | Passed as `-c model_reasoning_effort=<value>`. |
| `model` | `string` | `claude-code` | `"sonnet"` | Passed as `--model`. |
| `effort` | `string` | `claude-code` | `"high"` | Passed as `--effort`. |
| `permission_mode` | `string` | `claude-code` | `"dangerously-skip-permissions"` | `"plan"` uses `--permission-mode plan`; any other value uses `--dangerously-skip-permissions`. |
| `max_turns` | `int` | `claude-code` | `50` | Passed as `--max-turns`. |
| `timeout` | `int` | all backends | Chain default timeout | Per-step timeout override in seconds. |
| `output_schema` | `string` | both | unset | Codex: passed as `--output-schema`; Claude: if path exists inside step output dir, file contents are passed as `--json-schema`. |
| `extra_flags` | `list[string]` | both | `[]` | Appended to backend command argv. |

Validation behavior:
- `verify` steps must define `[steps.gate]`.
- `verify` steps must use `agent = "none"`.
- Non-verify steps with an agent backend must define `[steps.brief]`.
- Undefined template variables in brief text/path or gate command are errors.
- Missing gates on non-verify/non-custom steps are warnings.

## Backends
Built-in backends:

| Backend | `agent` value | Binary | Provider | Multi-model | Primary output | Telemetry | Token telemetry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Codex CLI | `codex-cli` | `codex` | OpenAI | No | `output.md` or `output.json` | `events.jsonl` | Yes |
| Claude Code | `claude-code` | `claude` | Anthropic | `--model` | `raw.json` | `raw.json` | Yes |
| Cursor CLI | `cursor-cli` | `cursor-wrapper` → `cursor-agent` | Multi (Anthropic, Google, others) | `--model` | `output.jsonl` | `output.jsonl` | No (upstream gap) |
| No-op | `none` | none | — | — | none | none | — |

### Backend discovery
`codex-cli` binary resolution order:
1. `AGENT_CHAIN_CODEX_BIN`
2. `codex` on `PATH`
3. `~/.local/bin/codex`

`claude-code` binary resolution order:
1. `AGENT_CHAIN_CLAUDE_BIN`
2. `claude` on `PATH`
3. `~/.local/bin/claude`

`cursor-cli` binary resolution order:
1. `AGENT_CHAIN_CURSOR_BIN`
2. `cursor-wrapper` on `PATH`
3. `scripts/cursor-wrapper.py` via `sys.executable` (repository-local fallback)

The wrapper script (`cursor-wrapper`) handles cursor-agent's process lifecycle quirks (no clean exit, positional prompt requirement, binary discovery).

### cursor-cli setup
```bash
# Install cursor-agent
curl https://cursor.com/install -fsSL | bash
# Authenticate
cursor-agent login
# Verify available models
cursor-agent --list-models
```

### cursor-cli options
| `agent_config` key | Type | Effect |
| --- | --- | --- |
| `model` | `string` | Model identifier (e.g. `opus-4.6`, `gemini-3.1-pro`). |
| `mode` | `string` | `plan` (read-only) or `ask` (Q&A, read-only). |
| `force` | `bool` | Allow file modifications (`--force`). Default: `true`. |
| `sandbox` | `string` | `enabled` or `disabled`. |
| `max_turns` | `int` | Maximum agent turns; omitted unless explicitly set. |
| `timeout` | `int` | Step timeout override. |
| `extra_flags` | `list[string]` | Extra CLI flags appended to command. |

### codex-cli options
| `agent_config` key | Type | Effect |
| --- | --- | --- |
| `sandbox` | `string` | `read-only` or full-auto mode selection. |
| `reasoning_effort` | `string` | Model reasoning effort setting. |
| `output_schema` | `string` | Structured output schema path passed to Codex CLI. |
| `timeout` | `int` | Step timeout override. |
| `extra_flags` | `list[string]` | Extra CLI flags appended to command. |

### claude-code options
| `agent_config` key | Type | Effect |
| --- | --- | --- |
| `model` | `string` | Claude model alias (`sonnet`, `opus`, etc.). |
| `effort` | `string` | Claude effort level. |
| `permission_mode` | `string` | `plan` mode or dangerous skip-permissions mode. |
| `max_turns` | `int` | Maximum turn count. |
| `output_schema` | `string` | Optional schema file content passed as `--json-schema` when allowed. |
| `timeout` | `int` | Step timeout override. |
| `extra_flags` | `list[string]` | Extra CLI flags appended to command. |

## CLI Reference
### `run`
```bash
agent-chain run [OPTIONS] CHAIN_FILE
```

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-o, --output-dir` | path | auto | Output directory for run artifacts. |
| `-v, --verbose` | flag | `false` | Print progress logs to stderr. |
| `--dry-run` | flag | `false` | Print planned execution without launching agents/gates. |
| `--timeout` | int | `1800` | Global timeout fallback in seconds. |
| `--start-from` | string | - | Resume execution from a named step; prior steps are marked SKIPPED. |
| `--var KEY=VALUE` | repeatable | - | Provide or override template variables. |

If `--output-dir` is omitted, output defaults to:

```text
.agent-chain/<chain-name>-<YYYYMMDDTHHMMSS>
```

### `validate`
```bash
agent-chain validate [OPTIONS] CHAIN_FILE
```

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--strict` | flag | `false` | Treat validation warnings as errors. |
| `--var KEY=VALUE` | repeatable | - | Variables used during template validation. |

### `report`
```bash
agent-chain report [OPTIONS] OUTPUT_DIR
```

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--format` | `text`, `json`, `markdown` | `text` | Render format. |
| `--include-telemetry` | flag | `false` | Include per-step token breakdowns. |

## Template Variables
Template syntax: `{{variable_name}}`.

Built-in runtime variables:

| Variable | Meaning |
| --- | --- |
| `chain.name` | Current chain name. |
| `chain.output_dir` | Absolute path to current run output directory. |
| `step.name` | Current step name. |
| `step.output_dir` | Absolute path to current step output directory. |
| `previous_step.name` | Previous step name, or empty for first step. |
| `previous_step.output_dir` | Previous step output dir, or empty for first step. |
| `previous_step.output_path` | Previous step primary artifact path, or empty. |
| `previous_step.status` | Previous step status string, or empty. |

Custom variables:
- Define in `[vars]`.
- Override from CLI with repeatable `--var KEY=VALUE`.

```toml
[vars]
project_root = "/repo"
mode = "ci"
```

```bash
agent-chain run chain.toml --var project_root=/tmp/repo --var mode=local
```

Resolution precedence at runtime:
1. `[vars]` values
2. `--var` values
3. Built-in runtime variables (`chain.*`, `step.*`, `previous_step.*`)

## Examples
The `examples/` directory includes ready-to-run chains:

```text
examples/codex-impl-review.toml
examples/review-only.toml
examples/full-pipeline.toml
examples/cursor-adversarial-review.toml
examples/live-tests/*.toml
```

### Example 1: verify-only
```toml
[chain]
name = "minimal"

[[steps]]
name = "check"
type = "verify"
agent = "none"

[steps.gate]
command = "echo ok"
```

### Example 2: codex implement then verify
```toml
[chain]
name = "codex-verify"
default_timeout = 1800

[[steps]]
name = "implement"
type = "implement"
agent = "codex-cli"

[steps.brief]
source = "inline"
text = "Implement the requested change."

[steps.agent_config]
sandbox = "full-auto"
reasoning_effort = "high"

[[steps]]
name = "verify"
type = "verify"
agent = "none"

[steps.gate]
command = "pytest -q"
expected_exit_code = 0
```

### Example 3: multi-agent pipeline
```toml
[chain]
name = "full-pipeline"
default_timeout = 1800

[[steps]]
name = "implement"
type = "implement"
agent = "codex-cli"
[steps.brief]
source = "inline"
text = "Implement feature."
[steps.agent_config]
sandbox = "full-auto"
reasoning_effort = "high"

[[steps]]
name = "review"
type = "review"
agent = "claude-code"
[steps.brief]
source = "inline"
text = "Review implementation and apply fixes."
[steps.agent_config]
model = "opus"
effort = "high"
permission_mode = "dangerously-skip-permissions"
max_turns = 50

[[steps]]
name = "fix-findings"
type = "fix"
agent = "claude-code"
[steps.brief]
source = "inline"
text = "Fix findings from {{previous_step.output_path}}"

[[steps]]
name = "verify"
type = "verify"
agent = "none"
[steps.gate]
command = "pytest -q"
expected_exit_code = 0
on_failure = "abort"
```

Run an example:

```bash
agent-chain validate examples/codex-impl-review.toml
agent-chain run -v examples/codex-impl-review.toml
```

## Development
Use the Makefile targets for local development. By default it uses `local.venv/bin/python` (override with `PYTHON_EXE=...`).

### Setup
```bash
python3.11 -m venv local.venv
source local.venv/bin/activate
python -m pip install -e '.[dev]'
```

### Commands
| Command | Description |
| --- | --- |
| `make help` | List available targets. |
| `make test` | Run pytest suite. |
| `make test-cov` | Run tests with terminal + HTML coverage (`coverage_html/`). |
| `make lint` | Run Ruff lint checks. |
| `make typecheck` | Run mypy and pyright. |
| `make typecheck-mypy` | Run mypy only. |
| `make typecheck-pyright` | Run pyright only. |
| `make format` | Apply Ruff fixes and format code. |
| `make all` | Run lint, typecheck, and tests. |
| `make clean` | Remove build/cache/test artifacts. |
| `make install` | Install editable package with dev dependencies. |
