# Chain Design Guide

This guide covers how to design an optimal multi-agent implementation chain for a coding task. It is the primary reference for chain planning.

## Design Process Overview

1. **Decompose the task** into components (schema changes, core implementation, integration, docs)
2. **Select the effort level** based on risk and importance
3. **Assign agents** to each component (workhorse vs quality agent)
4. **Group into phases** with review cycles
5. **Write briefs** at the appropriate depth for the effort level
6. **Configure chain-level settings** (timeout, working directory)
7. **Express as a chain definition** (see [operating.md](operating.md))

## Core Pattern: Implement → (Improve) → Review → Integrate

Every component in a chain follows a cycle. Two agents alternate every step — the same provider never runs two consecutive steps.

1. **Implement** — write the code or artifact (default: workhorse agent)
2. **Improvement pass** (when cross-provider, see below) — quality agent refines into codebase conventions
3. **Adversarial review** (standard+) — opposite-provider agent reviews for correctness, safety, design
4. **Review integration** (standard+) — quality agent addresses findings, verifies gates
5. **Second-round review** (thorough+) — re-review after fixes
6. **Second-round integration** (thorough+) — address second-round findings

The key property: **the reviewer is always a different provider/model than whoever last substantially edited the code.** Different model architectures have different blind spots.

**Important**: The chain runner executes exactly the steps declared in the definition file. The improvement pass, review, and integration are steps the chain designer explicitly includes — they are not automatically inserted by the tool. The patterns in this guide are conventions for the chain author to follow when designing the chain.

## Effort Levels

Effort is a holistic quality dial controlling three dimensions simultaneously:

- **Chain structure** — how many review rounds
- **Implementation brief depth** — how careful the implementing agent is instructed to be
- **Review brief depth** — how detailed the reviewer's focus areas are

Higher effort means more token consumption per step (agents think more, explore more, write more tests) — this is the correct tradeoff when the user dials up effort.

### `minimal` — implement only, 0 reviews

For low-risk changes where the gate is sufficient validation. The brief still expects reasonable quality.

**Chain structure:**

```text
implement → (improve) → [gate]
```

**Implementation briefs** include:

- Functional requirements
- Main-path tests
- Basic error handling

**Review briefs**: none (gate only).

### `standard` — one review round

The default for indie environments. "Do the job right" — edge cases handled, errors considered, decisions documented.

**Chain structure:**

```text
implement → (improve) → [gate] → adversarial-review → review-integration → [gate]
```

**Implementation briefs** include:

- Functional requirements
- Comprehensive tests including edge cases
- Thorough error handling
- Documented design decisions

**Review briefs** include:

- General adversarial review for correctness, safety, and design quality

### `thorough` — two review rounds

The default for enterprise environments, and for important indie work. Invest in exploration before coding. The second review round catches issues introduced by fixes.

**Chain structure:**

```text
implement → (improve) → [gate]
  → adversarial-review → review-integration → [gate]
  → second-review → second-integration → [gate]
```

**Implementation briefs** include:

- Functional requirements
- Consider alternative approaches and document reasoning
- Security implications analysis
- Comprehensive tests including boundary conditions and failure modes
- Documented design decisions and tradeoffs

**Review briefs** include:

- Adversarial review with specific focus areas: error handling completeness, test coverage gaps, API consistency with existing codebase, security considerations

### `comprehensive` — two review rounds + specialized final passes

For high-stakes work demanding deep analysis. The cross-cutting final review expands into multiple focused passes, each with a targeted checklist.

**Chain structure:**

```text
implement → (improve) → [gate]
  → adversarial-review → review-integration → [gate]
  → second-review → second-integration → [gate]
  → [specialized final passes — see Final Phase section]
```

**Implementation briefs** include:

- Everything in thorough
- Threat modeling
- Property-based or generative tests where applicable
- Long-term maintenance analysis
- Explicit documentation of rejected alternatives with reasoning

**Review briefs** include:

- Thorough-level general reviews for per-component cycles
- Final phase expands into multiple specialized review passes (e.g., security-focused, performance-focused, API-consistency-focused), each with a targeted checklist

### `exhaustive` — maximum quality investment

Reserved for spare-no-expense scenarios. The concrete pattern will be refined based on experience. Candidates include: parallel independent implementations compared, formal verification passes, extended exploration phases, red-team exercises.

## Cross-Provider Improvement Pass

**Design convention**: When the chain designer assigns the workhorse agent (a different provider than the quality agent) to implement a component, they should also add an improvement step where the quality agent refines the code into codebase conventions. This is not an effort choice — it's cross-provider integration cleanup.

The quality agent knows the codebase's style, import conventions, and test patterns. When a different-provider agent implements, the quality agent polishes before review. This produces cleaner reviews with fewer false positives about style.

**When the quality agent itself implements**, no improvement step is needed — the code is already in the codebase's voice, producing a shorter per-component cycle.

Under request-optimized profiles (enterprise), the improvement pass folds into the implementation brief ("Implement X. Then review your work for codebase style consistency before finishing.") rather than becoming a separate step.

## Step Shape: Token-Optimized vs Request-Optimized

Step shape is a fixed property of each profile, determined by billing model. It is not a user-facing choice.

### Token-optimized (indie profiles)

Token cost is the primary constraint. Request count doesn't matter.

- **Small, focused steps** with narrow scope and short briefs
- **One component per implementation step** — easier to debug failures, cheaper per-step
- **Independent review cycles** — each component reviewed before the next begins
- **Separate improvement pass step** when the workhorse implements
- **Final phase is two+ steps** (cross-cutting review + integration/postmortem)

More steps, lower per-step token usage. A failed step wastes fewer tokens.

### Request-optimized (enterprise profiles)

Request count is the primary constraint (e.g., 500 requests/engineer/month, unlimited tokens per request).

- **Larger, combined steps** merging related components when they share context
- **Fold improvement into implementation** — the brief includes polish instructions rather than a separate step
- **Combine review integration with next implementation** — the next brief starts with "First, address the findings from the previous review: [findings]. Then implement [next component]."
- **Final phase can be a single step** combining review response, testing, and postmortem
- **Prefer higher `max_turns`** over more steps — let the agent iterate within a single request

Fewer, larger steps. Each request does more work to conserve the monthly budget.

### Step counts by effort and shape

Lower counts when quality agent implements (no improvement step), higher when workhorse implements (improvement step added).

| Effort | Token-optimized (steps/component) | Request-optimized (steps/component) |
| --- | --- | --- |
| minimal | 1–2 | 1 |
| standard | 3–4 | 2 (integration folded into next step) |
| thorough | 5–6 | 3–4 (folds as above, second review kept separate) |
| comprehensive | 5–6 + specialized final passes | 3–4 + specialized final passes |

## Agent Assignment

Each profile defines two roles:

- **Workhorse agent** — default first-pass implementer. Typically has more budget or is better suited for raw implementation.
- **Quality agent** — improvement passes, review integration, docs. Typically the codebase's primary agent with stronger style/convention knowledge.

**Default**: The workhorse agent implements every component. The quality agent handles improvement, integration, and docs. The two agents alternate steps throughout the chain.

**Override — quality-agent implementation**: When a component heavily modifies existing code and benefits from deep codebase familiarity, the quality agent implements instead. Flag this per-component during chain design. No improvement step is needed, producing a shorter per-component cycle.

**Reviewer assignment**: The adversarial reviewer is always the opposite provider from whoever last substantially edited the code. In practice the two agents simply alternate.

### Choosing which agent implements

- **Workhorse (default)**: greenfield components, new modules, standalone scripts — a fresh architectural perspective adds value
- **Quality agent (override)**: components that touch many existing files, schema changes across backends, anything requiring deep codebase familiarity

## Phase Structure

Group related steps into phases. Each phase completes a self-contained component with its own review cycle before the next phase begins. End with a cross-cutting final review phase.

### Typical phase breakdown

1. **Foundation/prerequisite work** — schema changes, shared types, infrastructure
2. **Core implementation** — the main deliverable, often the largest component
3. **Integration** — wiring the core into the existing system
4. **Documentation and examples**
5. **Final review and postmortem** — cross-cutting review of all changes, test suite, process writeup

Not every task needs all five. Collapse phases when the task is small. A two-component task might be: Phase 1 (foundation + core), Phase 2 (final review).

## Brief Authoring

Briefs are the most important artifact in a chain. Agents cannot ask for clarification — the brief is all they get.

### Principles

1. **Spell out the decision tree.** If the agent will encounter a fork ("should I use approach A or B?"), make the decision for them or describe when to choose each.
2. **Distinguish firm constraints from flexible starting points.** "You must use X" vs "start with Y but change if needed."
3. **Set the bar for failure explicitly.** "If tests don't pass after 3 approaches, stop and report what you tried."
4. **Anticipate obstacles and plant workaround ideas.** If a particular API is tricky, say so.
5. **Match the effort level.** Higher effort means longer briefs that explicitly instruct the agent to invest more thinking. Don't write a `thorough` brief that says "implement X" — say "consider alternatives, analyze security, test boundaries."

### Implementation brief template

Placeholders in `{braces}` should be filled in by the chain designer. Variable references in the chain definition use double-brace syntax (see operating.md for details).

```markdown
# {Component Name}

## Objective
{What to build, in 1-2 sentences}

## Requirements
{Detailed functional requirements}

## Constraints
{Firm constraints: must-use interfaces, style rules, compatibility requirements}

## Design Guidance
{For standard+: document decisions as you go}
{For thorough+: consider alternatives before implementing, document reasoning}
{For comprehensive+: threat model, analyze maintenance implications}

## Testing
{For minimal: main-path tests}
{For standard: + edge cases}
{For thorough+: + boundary conditions, failure modes}
{For comprehensive: + property-based tests where applicable}

## Files to Modify
{List of expected files, or "determine based on requirements"}

## Gate
`make all` must pass.
```

### Review brief template

For review steps using claude-code, always set `permission_mode = "plan"` in the step's agent config to enforce read-only access. Without this, the reviewer can modify files despite the brief saying "do not modify."

```markdown
# Adversarial Review: {Component Name}

## Scope
Review all changes from the {component} implementation step.

## Review Focus
{For standard: correctness, safety, design quality}
{For thorough+: + error handling completeness, test coverage gaps, API consistency, security}

## Deliverable
Write findings as your output with:
- Severity (critical / major / minor / nit)
- File and line reference
- Description and recommended fix

Do NOT modify any source files. This is a read-only review.
```

### Review integration brief template

```markdown
# Review Integration: {Component Name}

## Context
Address the findings from the adversarial review in the previous step's output.

## Instructions
1. Read all findings
2. Address critical and major findings (fix the code)
3. Address minor findings where the fix is straightforward
4. For nits: fix if trivial, otherwise note as intentional with brief rationale
5. Verify `make all` passes after all changes

## Deliverable
Write a response documenting:
- Each finding and what was done (fixed / won't-fix with rationale)
```

### Postmortem brief template

```markdown
# Final Integration and Postmortem

## Context
Address findings from the cross-cutting adversarial review in the previous step's output.

## Instructions
1. Address all critical and major findings
2. Run the full test suite and verify everything passes
3. Write a process postmortem covering:
   - What worked well in the chain design
   - What didn't work (failed steps, inadequate briefs, missed requirements)
   - Recommendations for future chain designs
   - Token/time usage observations
```

## Gates

Every implementation and integration step should have a verification gate. Standard gates:

- `make all` — full lint + typecheck + test suite (most steps)
- `make lint` — lint only (docs-only steps)
- `make test` — tests only (when typecheck is slow and not relevant)

Review steps (read-only) do not have gates.

If the project doesn't use `make`, substitute the equivalent commands (e.g., `npm run lint && npm test`).

## Final Phase

At `standard` effort and above, every chain ends with a cross-cutting review phase:

1. **Entire-process adversarial review** — the review agent examines all changes holistically, not just the last component
2. **Final integration and postmortem** — the quality agent addresses final findings, runs the full test suite, and writes a process postmortem

At `comprehensive` effort, the final phase expands: the cross-cutting review splits into multiple specialized passes (e.g., security review, performance review, API consistency review), each as a separate step with a targeted checklist. The final integration step addresses all specialized findings.

When request-optimized, final-phase steps may be merged where feasible.

The postmortem is a first-class deliverable, not an afterthought. It captures what worked, what didn't, and what to change in future chain designs.

## Chain-Level Settings

- **`default_timeout`** — per-chain based on expected step complexity. Current system default is 1800 seconds (30 minutes). Override to something longer for implementation steps — 3600 (1 hour) is a reasonable starting point.
- **`max_turns`** — set per-step when needed. claude-code defaults to 50 turns if not specified. codex-cli has no default limit. When request-optimized, prefer higher `max_turns` over more steps.
- **`working_dir`** — point at a separate working copy to avoid modifying the design repo during execution. This is important: the chain definition and briefs typically live in a design repo, while the implementation work happens in a separate clone.

## Naming Conventions

### Step names

Follow the pattern `{component}-{role}`:

- `cursor-wrapper-implementation` (implement, workhorse)
- `cursor-wrapper-improvement` (improve, quality agent)
- `cursor-wrapper-adversarial-review` (review)
- `cursor-wrapper-review-integration` (integrate, quality agent)

For second-round reviews at thorough+:

- `cursor-wrapper-second-review`
- `cursor-wrapper-second-integration`

### Brief files

Follow `{NN}-{step-name}.md` in a `{chain-name}-briefs/` directory alongside the chain definition:

```text
workflow/
├── my-feature-chain.toml
└── my-feature-chain-briefs/
    ├── 01-schema-expansion.md
    ├── 02-schema-adversarial-review.md
    ├── 03-schema-review-integration.md
    ├── 04-core-implementation.md
    └── ...
```

## Model Versions

Specific model versions (Opus 4.6, Codex 5.3, Gemini 3.1 Pro) reflect SOTA at time of writing (2026-02-28). Update the profile when newer models are available — the pattern is stable, the model choices evolve.
