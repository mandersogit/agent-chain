---
name: agent-chain
description: Design and operate multi-agent implementation chains. Use when planning a multi-step coding task that should be broken into agent steps with reviews, when choosing effort levels and agent assignments for a chain, when writing chain definitions or step briefs, when running or troubleshooting agent-chain executions, or when the user mentions agent-chain, chain design, effort levels, or adversarial review patterns.
---

# agent-chain

agent-chain is a CLI tool for orchestrating sequences of AI coding agents. It runs declarative pipelines where each step invokes an agent with a brief, collects telemetry, and optionally runs a verification gate before proceeding.

## Key Concepts

- **Chain** — a definition file declaring an ordered sequence of steps, each targeting an agent backend
- **Step** — one agent invocation: an implementation, review, fix, or verification task
- **Brief** — the instructions given to an agent for a step (inline text or a file)
- **Gate** — a shell command run after a step to verify success (e.g., `make all`)
- **Backend** — an agent harness (e.g., `claude-code`, `codex-cli`) or `none` for verification-only steps
- **Profile** — an environment configuration defining available harnesses, agent roles, and defaults

## Current Backends

- `claude-code` — Anthropic's Claude Code CLI
- `codex-cli` — OpenAI's Codex CLI
- `none` — no agent invocation (for `verify` steps that only run a gate)

Additional backends (e.g., `cursor-cli`) are planned. The enterprise profile describes a future state where cursor-cli is available.

## When to Use This Skill

### Planning a chain

When a user asks to design, plan, or create an agent-chain for a task, read:

1. [references/planning.md](references/planning.md) — the comprehensive chain design guide
2. The appropriate profile for the target environment:
   - [references/profile-indie.md](references/profile-indie.md) — multi-provider, individual/small-business
   - [references/profile-enterprise.md](references/profile-enterprise.md) — single-harness, enterprise security constraints (requires cursor-cli backend — not yet implemented)

### Operating the tool

When a user asks to write chain definitions, run a chain, or interpret results, read:

- [references/operating.md](references/operating.md) — definition syntax, CLI commands, output structure, troubleshooting

## Quick Reference: Effort Levels

The user specifies an effort level to control quality investment. If not specified, the profile default applies.

| Level | Reviews | Implementation depth | Default for |
| --- | --- | --- | --- |
| `minimal` | 0 | Main-path tests, basic error handling | — |
| `standard` | 1 round | + edge cases, documented decisions | indie |
| `thorough` | 2 rounds | + alternative analysis, security, boundaries | enterprise |
| `comprehensive` | 2 rounds + specialized | + threat modeling, property tests, maintenance | — |
| `exhaustive` | TBD | Maximum investment | — |

## Quick Reference: The Core Cycle

At `standard` effort and above, each component follows this cycle (length varies by effort):

```text
workhorse implements → (quality agent improves) → reviewer reviews → quality agent integrates
```

At `minimal` effort, the cycle is just: implement → (improve) → gate.

The improvement pass is a **chain design convention**: when the chain author assigns the workhorse agent to implement, they also add an improvement step for the quality agent. This is not a runtime feature — the chain runner executes exactly the steps declared in the definition. The improvement pass is inserted by the chain designer, not by the tool.

The reviewer is always the opposite provider from whoever last edited the code.
