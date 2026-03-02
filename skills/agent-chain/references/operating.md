# Operating agent-chain

This reference covers the mechanics of expressing a chain design as a definition file, running it, and interpreting results.

> **Note on definition format**: agent-chain currently uses TOML for chain definitions. A migration to YAML with a different templating system is planned. The examples below use the current TOML format. The concepts (chain metadata, step entries, brief configuration, gates) will carry over to the new format — only the surface syntax will change.

## Chain Definition Syntax

A chain definition is a TOML file with three sections: `[chain]` metadata, optional `[vars]`, and `[[steps]]` entries.

### Minimal example

```toml
[chain]
name = "my-feature"
description = "Implement feature X"
working_dir = "/path/to/working-copy"
default_timeout = 3600

[[steps]]
name = "implementation"
type = "implement"
agent = "claude-code"

[steps.brief]
source = "file"
path = "my-feature-briefs/01-implementation.md"

[steps.agent_config]
max_turns = 50

[steps.gate]
command = "make all"
expected_exit_code = 0
```

### `[chain]` table

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Chain name, used in output directory naming |
| `description` | string | no | Human-readable description |
| `working_dir` | string | no | Working directory for step execution (default: chain file's directory) |
| `default_timeout` | int | no | Per-step timeout in seconds (default: 1800) |

### `[vars]` table

Template variables available for substitution in brief paths, brief text, and gate commands. Variables use `{{variable_name}}` syntax.

```toml
[vars]
project_name = "agent-chain"
target_branch = "feature/cursor-cli"
```

### `[[steps]]` entries

Each `[[steps]]` is one step in the chain, executed in order.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Unique step name |
| `type` | string | yes | One of: `implement`, `review`, `fix`, `verify`, `custom` |
| `agent` | string | yes | Backend name: `claude-code`, `codex-cli`, or `none` |

### `[steps.brief]` — step instructions

| Field | Type | Description |
| --- | --- | --- |
| `source` | string | `"file"` or `"inline"` |
| `path` | string | Path to brief file (when `source = "file"`), relative to chain file location |
| `text` | string | Inline brief text (when `source = "inline"`) |

File briefs support variable substitution in the path: `path = "briefs/{{step.name}}.md"`

### `[steps.agent_config]` — backend configuration

| Field | Type | Description |
| --- | --- | --- |
| `model` | string | Model to use (backend-specific) |
| `sandbox` | string | Sandbox mode (`codex-cli`: `full`, `semi`, or `none`) |
| `permission_mode` | string | Permission mode (`claude-code`): `"plan"` for read-only review steps |
| `reasoning_effort` | string | Reasoning effort level (codex-cli) |
| `max_turns` | int | Maximum agent turns (claude-code defaults to 50 if not set) |
| `timeout` | int | Per-step timeout override (seconds) |
| `output_schema` | string | Path to JSON schema for structured output |
| `extra_flags` | list | Additional CLI flags passed to the backend |

**Review steps**: Always set `permission_mode = "plan"` for claude-code review steps. This enforces read-only access at the CLI level, preventing the reviewer from modifying files even if the brief says "do not modify." codex-cli has sandbox modes for similar enforcement.

### `[steps.gate]` — verification gate

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `command` | string | — | Shell command to run |
| `expected_exit_code` | int | 0 | Exit code that indicates success |
| `on_failure` | string | `"abort"` | What to do on failure: `"abort"`, `"warn"`, or `"skip"` |

### Built-in variables

These are always available for substitution in briefs and gate commands:

| Variable | Description |
| --- | --- |
| `{{chain.name}}` | Chain name from `[chain]` |
| `{{chain.output_dir}}` | Absolute path to the chain's output directory |
| `{{step.name}}` | Current step name |
| `{{step.output_dir}}` | Absolute path to current step's output directory |
| `{{previous_step.name}}` | Previous step's name (empty if first step) |
| `{{previous_step.output_dir}}` | Previous step's output directory |
| `{{previous_step.output_path}}` | Previous step's output artifact path |
| `{{previous_step.status}}` | Previous step's status (success, failed, etc.) |

### Step types

- **`implement`** — create new code or artifacts. Requires a brief and an agent.
- **`review`** — read-only review. Use `permission_mode = "plan"` for claude-code to prevent modifications. Requires a brief.
- **`fix`** — address review findings or make corrections. Requires a brief.
- **`verify`** — gate-only step, no agent invocation. Must use `agent = "none"` and must have a gate.
- **`custom`** — escape hatch for steps that don't fit the other types.

## CLI Commands

### `agent-chain run`

```bash
agent-chain run <chain-file> [options]
```

| Option | Description |
| --- | --- |
| `-o, --output-dir DIR` | Output directory (default: `.agent-chain/{name}-{timestamp}`) |
| `-v, --verbose` | Print step progress to stderr |
| `--dry-run` | Print commands without executing |
| `--timeout SECONDS` | Global per-step timeout override (default: 1800) |
| `--var KEY=VALUE` | Set a template variable (repeatable) |

### `agent-chain validate`

```bash
agent-chain validate <chain-file> [--strict] [--var KEY=VALUE]
```

Checks TOML syntax, step structure, variable references, and backend availability. With `--strict`, warnings become errors.

### `agent-chain report`

```bash
agent-chain report <output-dir> [--format text|json|markdown] [--include-telemetry]
```

Display results from a completed chain run.

## Output Structure

Each run creates an output directory. The exact filenames within each step directory depend on the backend:

```text
.agent-chain/my-feature-20260228T143000/
├── report.json                 # Overall chain report
├── DONE                        # Sentinel file with chain status
└── steps/
    ├── implementation/
    │   ├── brief.md            # Resolved brief (with variables substituted)
    │   ├── output.md           # Agent output (codex-cli) — or raw.json (claude-code)
    │   ├── events.jsonl        # Telemetry (codex-cli) — or raw.json (claude-code)
    │   ├── stderr.log          # Agent stderr
    │   ├── gate-stdout.log     # Gate command stdout
    │   └── gate-stderr.log     # Gate command stderr
    ├── adversarial-review/
    │   ├── brief.md
    │   ├── raw.json            # Claude-code output + telemetry in single file
    │   └── stderr.log
    └── review-integration/
        └── ...
```

Backend-specific output files:

- **codex-cli**: `output.md` (agent output), `events.jsonl` (telemetry)
- **claude-code**: `raw.json` (combined output and telemetry)

## Execution Flow

1. **Validate** the chain definition (structure, variables, backend availability)
2. **Create** the output directory
3. **For each step**, in order:
   a. Resolve variables and write the brief to `steps/{name}/brief.md`
   b. Build the backend command
   c. Launch the agent subprocess (stdin=brief, stdout=telemetry, stderr=log)
   d. Wait for completion (with timeout)
   e. Parse telemetry
   f. Run the gate command (if configured)
   g. If gate fails and `on_failure = "abort"`, stop the chain
4. **Write** the final report to `report.json` and a `DONE` sentinel file

## Timeout Cascade

Timeout is resolved in priority order:

1. Per-step `timeout` in `[steps.agent_config]`
2. Chain-level `default_timeout` in `[chain]`
3. CLI `--timeout` flag
4. System default: 1800 seconds (30 minutes)

`timeout = 0` means no limit (the step runs until the agent finishes or is interrupted).

For long-running steps, set `default_timeout` at the chain level or override per-step. The system default of 30 minutes is a safety net — most implementation steps should specify a longer timeout.

## Signal Handling

- **First Ctrl-C (SIGINT)**: forwarded to the active agent process via process group signal
- **Second Ctrl-C within 1 second**: sends SIGTERM to the agent process tree, then SIGKILL after a grace period; marks the chain as interrupted
- **SIGTERM**: forwarded to the active agent process and marks the chain as interrupted
- Remaining steps after interruption are marked `NOT_STARTED`
- The report is always written, even on interruption

## Troubleshooting

### Step fails with CONFIG_ERROR

The brief file wasn't found, a variable is undefined, or the backend command couldn't be built. Check:

- Brief file path is relative to the chain file's directory
- All `{{variables}}` are defined in `[vars]` or via `--var`
- The agent backend is installed and in PATH

### Step times out

The agent exceeded the timeout. Options:

- Increase `timeout` in `[steps.agent_config]` for that step
- Increase `default_timeout` in `[chain]`
- Simplify the brief (the step may be too large)

### Gate fails

The verification command returned a non-expected exit code. Check `gate-stdout.log` and `gate-stderr.log` in the step's output directory for details.

### Agent produces no output

Check `stderr.log` for errors. Common causes:

- Agent not authenticated (run the backend's auth/login command)
- Model not available (API outage, rate limit)
- Brief is empty or malformed
