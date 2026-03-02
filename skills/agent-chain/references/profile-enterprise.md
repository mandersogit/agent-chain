# Profile: enterprise

> **Prerequisite**: This profile requires the `cursor-cli` backend, which is planned but not yet implemented. The design patterns described here are ready for use once the backend is available.

Single-harness environment with enterprise security and data-protection constraints. Typically provided through a managed platform (e.g., cursor-agent via CEGAI) where all model access goes through a single tool. Cross-provider diversity is achieved by selecting different models within that tool.

## Environment

- **Available harnesses**: `cursor-cli` (cursor-agent) — **planned, not yet implemented**
- **Default effort**: `thorough`
- **Step shape**: request-optimized (fixed monthly request budget, unlimited tokens per request)
- **Budget constraint**: ~500 requests/engineer/month

## Agent Roles

| Role | Harness / Model | Rationale |
| --- | --- | --- |
| Workhorse (default implementer) | cursor-cli / opus-4.6 | SOTA Anthropic model, strongest implementation |
| Quality agent | cursor-cli / opus-4.6 | Same model (single-harness environment) |
| Adversarial reviewer | cursor-cli / gemini-3.1-pro | Google model provides independent review perspective |

### Why opus is both workhorse and quality agent

In enterprise, the harness is fixed (cursor-cli) and opus is the strongest available model. There's no cost benefit to splitting roles across models for implementation work — opus handles both first-pass and polish. The cross-provider benefit comes entirely from gemini doing adversarial reviews, where a different model architecture catches different blind spots.

**Consequence**: No cross-provider improvement step is generated (workhorse = quality agent). Every default implementation produces a shorter cycle than indie.

### Cross-provider review

The adversarial reviewer (gemini) is always a different model from the implementer (opus). This is the primary quality mechanism in enterprise — different providers find different issues.

## Default Flows

### Default flow (thorough effort, request-optimized)

With request optimization, steps are folded to conserve the monthly request budget:

```text
opus implements → [gate]
  → gemini reviews
  → opus integrates + next-component-prep → [gate]
  → gemini second-reviews
  → opus second-integrates → [gate]
```

Review integration is folded into the next implementation step's brief where possible: "First, address the findings from the previous review. Then implement [next component]."

### Step count with request optimization

Because improvement steps don't apply (workhorse = quality agent) and integration folds into next steps:

| Effort | Steps/component (request-optimized) | Notes |
| --- | --- | --- |
| minimal | 1 | Implement only |
| standard | 2 | Implement + review (integration folded into next step) |
| thorough | 3–4 | + second review round (kept separate) |
| comprehensive | 3–4 + specialized final passes | Specialized reviews in final phase |

### Why thorough is the default

With unlimited tokens per request, two review rounds cost only one extra request per component — cheap insurance. There is no reason to optimize tokens in this profile. The only tradeoff is time vs quality:

- **Time-constrained**: drop to `standard` (1 review round)
- **Quality-maximizing**: use `comprehensive` (specialized final passes)

## Request Budget Planning

With ~500 requests/month, plan chains carefully:

| Chain size | Effort | Approx. requests | Budget % (of 500) |
| --- | --- | --- | --- |
| Small (2 components) | thorough | 8–10 | 2% |
| Medium (4 components) | thorough | 16–20 | 4% |
| Large (8 components) | thorough | 30–40 | 8% |
| Large (8 components) | comprehensive | 40–55 | 11% |

These are estimates. Actual request count depends on how aggressively steps are folded.

### Strategies to conserve requests

1. **Fold integration into next step.** The review-integration brief becomes the preamble to the next implementation brief.
2. **Combine related components.** If two components share significant context, implement them in one step with a longer brief.
3. **Use higher `max_turns`.** Let the agent iterate within a single request rather than splitting into multiple steps.
4. **Merge final-phase steps.** Combine the cross-cutting review response, testing, and postmortem into a single step.

## Configuration Notes

- **`default_timeout`**: 7200 (2 hours) is reasonable. Request-optimized steps are larger and take longer. Individual steps rarely exceed 1 hour, but budget headroom generously.
- **`max_turns`**: Higher than indie — set 100+ for large implementation steps. The agent should iterate freely within a single request. Only constrain if a specific model is known to loop.
- **`working_dir`**: Same principle as indie — separate clone for implementation work.
- **`model` in `agent_config`**: Specify the model explicitly for each step to control which provider runs. Example: `model = "opus-4.6"` for implementation, `model = "gemini-3.1-pro"` for reviews.

## Security Considerations

Enterprise profiles typically operate under constraints:

- All code passes through the managed platform's security boundary
- Model selection may be restricted to approved providers
- Audit logging requirements may apply
- Data residency constraints may limit which models can see which code

These constraints are environment-specific. The chain design pattern is the same regardless — only the harness configuration and model selection differ.
