# Profile: indie

Multi-provider environment for individuals and small businesses. Multiple provider subscriptions muxed together to spread token costs and get different architectural perspectives. No enterprise security or data-protection constraints on which providers can see the code.

## Environment

- **Available harnesses**: `claude-code`, `codex-cli`
- **Default effort**: `standard`
- **Step shape**: token-optimized (pay per token, request count doesn't matter)

## Agent Roles

| Role | Harness / Model | Rationale |
| --- | --- | --- |
| Workhorse (default implementer) | codex-cli / Codex 5.3 | More daily budget, effective at raw implementation |
| Quality agent | claude-code / Opus | Codebase conventions, polish, integration, docs |
| Adversarial reviewer | (alternates) | Whichever agent didn't last edit |

### Why codex-cli is the default implementer

codex-cli has the largest daily token budget on indie setups. Defaulting to it for first-pass implementation reserves claude-code budget for the higher-leverage work where its codebase knowledge matters most: improvement passes, review integration, documentation, and any component that touches many existing files.

This also means **every default implementation is followed by a cross-provider improvement step** by claude-code — the chain designer adds the workhorse's implementation step, then the quality agent's polish step, before the review. This is the intended pattern: it's both cost-efficient and produces better code.

### When to use claude-code as implementer instead

Override to claude-code implementation when a component:

- Touches many existing files across the codebase (schema changes, refactors)
- Requires deep familiarity with established patterns and conventions
- Is primarily modification of existing code rather than new code

When claude-code implements, no improvement step is needed (the code is already in the codebase's voice), producing a shorter cycle: 3 steps instead of 4 per component at `standard` effort.

## Default Flows

### Default: workhorse implements (standard effort)

4 steps per component:

```text
codex-cli implements → [gate]
  → claude-code improves → [gate]
  → codex-cli reviews
  → claude-code integrates → [gate]
```

### Override: quality agent implements (standard effort)

3 steps per component:

```text
claude-code implements → [gate]
  → codex-cli reviews
  → claude-code integrates → [gate]
```

### Workhorse implements (thorough effort)

6 steps per component:

```text
codex-cli implements → [gate]
  → claude-code improves → [gate]
  → codex-cli reviews
  → claude-code integrates → [gate]
  → codex-cli second-reviews
  → claude-code second-integrates → [gate]
```

## Step Count Estimates

For a task with N components (plus a final review phase):

| Effort | Workhorse implements | Quality implements | Final phase | Example: 3 components (2 workhorse, 1 quality) |
| --- | --- | --- | --- | --- |
| minimal | 2/component | 1/component | 0 | 5 |
| standard | 4/component | 3/component | 2 | 13 |
| thorough | 6/component | 5/component | 2 | 19 |
| comprehensive | 6/component | 5/component | 4+ | 21+ |

These are planning estimates. Actual step count depends on how many components need workhorse vs quality-agent implementation.

## Cost Characteristics

- **Token cost scales with effort level and step count.** Higher effort = more tokens per step (longer briefs, more agent thinking) AND more steps (more review rounds).
- **Failed steps waste tokens.** Token-optimized step shape minimizes waste by keeping each step small and focused.
- **Reviews are read-only** and generally cheaper than implementation steps.
- **Improvement steps** add token cost but reduce review findings, often netting out.

## Configuration Notes

- **`default_timeout`**: 3600 (1 hour) is reasonable for most indie steps. Individual implementation steps rarely exceed 30 minutes; set higher if the component is very large.
- **`max_turns`**: Omit (no limit) for codex-cli. For claude-code, the backend defaults to 50 if not set in `agent_config`. Increase for large implementation steps. Trust the agent by default.
- **`working_dir`**: Always point at a separate clone. The chain definition and briefs live in the design repo; implementation happens in the working copy.
