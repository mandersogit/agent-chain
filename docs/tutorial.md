# agent-chain Tutorial

Welcome! This tutorial will guide you through setting up and running your first multi-agent chain. agent-chain is a CLI tool that orchestrates sequential AI agent tasks, handling process management, verification, and reporting.

## 1. Prerequisites

Before you begin, ensure you have:

- **Python 3.11+** — Check with: `python3 --version`
- **At least one agent CLI installed:**
  - `claude` — Claude Code from Anthropic
  - `codex` — Codex CLI

Verify your agent is installed and on your PATH:

```bash
which claude     # or: which codex
claude --version
```

## 2. Installation

Clone the repository and set up your virtual environment:

```bash
# Clone the repo
git clone https://github.com/manderso/agent-chain.git
cd agent-chain

# Create and activate venv
python3.11 -m venv local.venv
source local.venv/bin/activate  # On Windows: local.venv\Scripts\activate

# Install agent-chain in development mode
pip install -e .
```

Verify installation:

```bash
agent-chain --version
agent-chain --help
```

## 3. Your First Chain

A chain is a sequence of steps defined in a TOML file. Each step delegates work to an AI agent (`claude-code`, `codex-cli`, or `none`). Let's create a simple 2-step chain: review code quality, then verify success.

Create a file `my-first-chain.toml`:

```toml
[chain]
name = "my-first-review"
description = "Review a project for code quality issues"
default_timeout = 1800

[[steps]]
name = "review"
type = "review"
agent = "claude-code"

  [steps.brief]
  source = "inline"
  text = "Review the project codebase for code quality issues. Look for: unclear naming, missing error handling, performance concerns, and security issues. Be concise."

  [steps.agent_config]
  model = "haiku"
  effort = "medium"
  permission_mode = "plan"
  max_turns = 10

[[steps]]
name = "verify"
type = "verify"
agent = "none"

  [steps.gate]
  command = "echo 'Chain completed successfully'"
  expected_exit_code = 0
```

This chain:
- **Step 1 (review):** Uses Claude Haiku (fast, cheap) to review code in plan mode (read-only)
- **Step 2 (verify):** Runs a simple shell command to confirm completion (no agent needed)

## 4. Running the Chain

First, validate your chain definition:

```bash
agent-chain validate my-first-chain.toml
# Valid: my-first-review (2 steps)
# Warning: Step 'review' (type=review, non-verify) has no verification gate configured
```

Then run it with verbose output:

```bash
agent-chain run my-first-chain.toml -v
```

You'll see step-by-step progress:

```
Step: review (type=review, agent=claude-code)
PID 12345 started. Timeout: 1800s.
PID 12345 exited with code 0 (322.3s)
Step "review" completed successfully.
Step: verify (type=verify, agent=none)
Gate: echo 'Chain completed successfully'
Gate passed (exit code 0)
Step "verify" completed successfully.
Chain "my-first-review" completed successfully.
Report: /home/user/.agent-chain/my-first-review-20260225T143000/report.json
```

## 5. Reading Results

Results are stored in `.agent-chain/my-first-review-TIMESTAMP/`:

```
.agent-chain/my-first-review-20260225T143000/
├── report.json          # Structured results (JSON)
├── DONE                 # Sentinel file: "success", "success_warnings", "gate_failed", "failed", or "interrupted"
└── steps/
    ├── review/
    │   ├── brief.md     # Resolved brief text
    │   ├── raw.json     # Agent output + telemetry
    │   └── stderr.log
    └── verify/
        └── gate-stdout.log
```

View the human-readable report:

```bash
agent-chain report /home/user/.agent-chain/my-first-review-20260225T143000 --format text
```

Or read the raw JSON for machine processing:

```bash
cat /home/user/.agent-chain/my-first-review-20260225T143000/report.json | jq .
```

## 6. Template Variables

Chains support variable substitution. Use `{{var_name}}` in briefs and gate commands:

```toml
[chain]
name = "project-review"

[vars]
project_name = "my-app"
project_root = "/home/user/my-app"

[[steps]]
name = "review"
type = "review"
agent = "claude-code"

  [steps.brief]
  source = "inline"
  text = "Review {{project_name}} codebase. Focus on correctness and security."

  [steps.agent_config]
  model = "sonnet"

[[steps]]
name = "check-build"
type = "verify"
agent = "none"

  [steps.gate]
  command = "cargo test --manifest-path {{project_root}}/Cargo.toml"
  expected_exit_code = 0
```

Override variables from the CLI:

```bash
agent-chain run project-review.toml \
  --var project_root=/path/to/other/project \
  --var project_name="other-app" \
  -v
```

**Built-in variables** available in all briefs:
- `{{step.name}}` — Current step name
- `{{chain.output_dir}}` — Output directory path
- `{{previous_step.name}}` — Previous step's name (empty if first step)
- `{{previous_step.output_path}}` — Path to previous step's output file

## 7. Multi-Step Pipeline

Upgrade to a 3-step chain: implement → review → verify. Here's an example:

```toml
[chain]
name = "implement-and-review"
description = "Implement a feature and review it for quality"

[[steps]]
name = "implement"
type = "implement"
agent = "claude-code"

  [steps.brief]
  source = "inline"
  text = "Write a simple Python function that returns the factorial of n."

  [steps.agent_config]
  model = "haiku"
  effort = "high"
  permission_mode = "dangerously-skip-permissions"
  max_turns = 20

[[steps]]
name = "review"
type = "review"
agent = "claude-code"

  [steps.brief]
  source = "inline"
  text = "Review the implementation for correctness, edge cases, and code style."

  [steps.agent_config]
  model = "haiku"
  effort = "medium"
  permission_mode = "plan"

[[steps]]
name = "verify"
type = "verify"
agent = "none"

  [steps.gate]
  command = "echo 'All steps completed'"
  expected_exit_code = 0
```

Each step runs sequentially. The output of one step is accessible in the next via `{{previous_step.output_path}}`.

## 8. Troubleshooting

### "Agent binary not found"
```
Error: codex binary not found. Check that 'codex' is on your PATH.
```
**Solution:** Ensure the agent CLI is installed and on your PATH. Check `which claude` or `which codex`. If needed, set the env var:
- For claude: `export AGENT_CHAIN_CLAUDE_BIN=/path/to/claude`
- For codex: `export AGENT_CHAIN_CODEX_BIN=/path/to/codex`

### "Brief file not found"
```
Error: Brief file not found: tasks/implement.md
```
**Solution:** Brief paths must be relative to the chain file directory (or absolute paths within the base directory). Check the path exists relative to your chain file location: `ls tasks/implement.md`.

### Step times out
```
Error: Step "implement" timed out after 1800 seconds.
```
**Solution:** Increase the timeout. Either:
- In the chain file: `default_timeout = 3600` (recommended — applies to all steps)
- Or per-step in the chain file: `timeout = 3600` under `[steps.agent_config]`
- Or on the CLI: `agent-chain run chain.toml --timeout 3600` (only affects steps without explicit timeout)

### Chain aborts unexpectedly
```
[14:35:22] Gate failed: exit code 1 (expected 0)
[14:35:22] on_failure = abort. Stopping chain.
```
**Solution:** Check the gate command output in `steps/<name>/gate-stderr.log`. Fix the command or set `on_failure = "warn"` to continue past gate failures.

### No output files
```
Error: Agent produced no output. Check stderr.log.
```
**Solution:** Review `steps/<step_name>/stderr.log` for agent errors. Check that:
- Agent has write permission in the output directory
- Brief is valid and not too long
- Agent model is spelled correctly (`haiku`, `sonnet`, `opus`)

### Can't find reports
Chains store results in `.agent-chain/<name>-<timestamp>/`. Find the latest run:

```bash
ls -ltd .agent-chain/my-first-review-* | head -1 | awk '{print $NF}'
```

---

## Next Steps

- Read the [design document](../workflow/2026-02-25-agent-chain-tool-design.md) for deep-dive architecture details
- Explore example chains in `examples/`
- Join the community and report issues on GitHub
