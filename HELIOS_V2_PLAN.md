# Helios v2 — Behavioral Science Implementation Plan

**Started**: 2026-03-10 23:26
**Target**: 2026-03-11 06:30 (~7 hours, ~28 iterations at 15min)
**Branch**: helios-v2-behavioral-science

---

## Vision

Helios v2 is a behavioral harness for AI agents. It wraps any agent as transparent middleware.
The agent has no awareness of it. Helios injects behavioral context before every session and
observes every output after. It is the behavioral biography of one agent across its lifetime.

**Core scientific commitments:**
- Behaviors are probability distributions over discrete named states (not strings, not scalars)
- Four behavioral dimensions: epistemic style, interaction agency, communication register, risk/caution
- Learning is negotiated: observe → detect drift → natural language summary → human decides → git commit
- Inheritance is KL-divergence minimizing blend (not weighted average)
- Identity is a four-level hierarchy: species → domain → user → session
- Delivery for Claude Code: MCP server + hooks (zero changes to Claude Code itself)

---

## Behavioral Taxonomy (LOCKED — do not change without updating all downstream)

### Dimension 1: Epistemic Style
How the agent handles uncertainty and the boundaries of its knowledge.
States: `confident` | `hedging` | `admits_ignorance` | `speculating`

### Dimension 2: Interaction Agency
How autonomous the agent acts — does it ask or assume, lead or follow.
States: `asks_first` | `assumes_and_acts` | `offers_options` | `decides_unilaterally` | `defers_to_user`

### Dimension 3: Communication Register
The formality, density, and structure of outputs.
States: `terse` | `moderate` | `thorough` | `technical_dense` | `plain_accessible`

### Dimension 4: Risk and Caution Profile
How the agent weighs safety vs speed, boldness vs conservatism.
States: `acts_immediately` | `checks_before_acting` | `warns_frequently` | `refuses_ambiguity`

---

## New YAML Schema for Behavioral Profiles

```yaml
# ~/.helios/base/identity.yaml
schema_version: "2.0"
level: "species"          # species | domain | user | session
agent_id: "helios-base"

behavioral_distributions:
  epistemic_style:
    confident: 0.50
    hedging: 0.25
    admits_ignorance: 0.15
    speculating: 0.10

  interaction_agency:
    asks_first: 0.40
    assumes_and_acts: 0.20
    offers_options: 0.25
    decides_unilaterally: 0.05
    defers_to_user: 0.10

  communication_register:
    terse: 0.20
    moderate: 0.40
    thorough: 0.25
    technical_dense: 0.10
    plain_accessible: 0.05

  risk_caution:
    acts_immediately: 0.20
    checks_before_acting: 0.40
    warns_frequently: 0.25
    refuses_ambiguity: 0.15

inheritance:
  parent: null              # null for species level
  kl_blend_weight: null     # null for species (no blending needed)

metadata:
  created: "2026-03-10"
  observation_count: 0
  last_negotiation: null
```

---

## Architecture — New Files to Build

### New Core Modules

| File | Purpose | Priority |
|------|---------|----------|
| `src/helios_mcp/taxonomy.py` | Defines the 4 dimensions, their states, and validation | P0 |
| `src/helios_mcp/distribution.py` | BehavioralDistribution type, KL-divergence, blending | P0 |
| `src/helios_mcp/observer.py` | 4-signal observation engine (structural+semantic+decision+user) | P1 |
| `src/helios_mcp/drift.py` | KL-divergence tracking, threshold detection, change events | P1 |
| `src/helios_mcp/negotiation.py` | Natural language drift summary + proposal generation | P2 |
| `src/helios_mcp/harness.py` | Agent wrapper — Python decorator + MCP proxy support | P2 |
| `src/helios_mcp/renderer.py` | Converts behavioral distributions to system prompt text | P1 |
| `src/helios_mcp/hierarchy.py` | 4-level identity hierarchy with KL-blend inheritance | P1 |

### Modified Existing Modules

| File | Change |
|------|--------|
| `src/helios_mcp/inheritance.py` | Replace weighted average with KL-divergence blend |
| `src/helios_mcp/config.py` | New schema v2, distribution loading/saving |
| `src/helios_mcp/learning.py` | Update to work with distributions |
| `src/helios_mcp/server.py` | Add observe_interaction, get_drift_report, negotiate tools |
| `src/helios_mcp/bootstrap.py` | Bootstrap with v2 schema and default distributions |

### Claude Code Delivery (MCP + Hooks)

Helios registers as an MCP server. Claude Code picks it up automatically.
- `get_behavioral_context(persona)` → rendered system prompt text injected at session start
- `observe_interaction(messages)` → called by PostToolUse hook after each tool call
- `get_drift_report(persona)` → returns NL summary when drift threshold crossed
- `negotiate_update(persona, accept|reject|modify)` → commits or discards proposed update

Users add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "helios": { "command": "uvx", "args": ["helios-mcp"] }
  }
}
```

---

## Implementation Phases and Tasks

### PHASE 0 — Foundation (Hours 1-1.5)
**Goal**: Scientific data types exist and are tested.

- [ ] P0.1 Create `taxonomy.py` — BEHAVIORAL_TAXONOMY dict, validate_state(), list_dimensions()
- [ ] P0.2 Create `distribution.py` — BehavioralDistribution class with:
  - `__init__(dimension, states_dict)` — validates sums to 1.0
  - `kl_divergence(other)` — D_KL(self || other)
  - `kl_blend(other, weight)` — KL-divergence minimizing mixture
  - `to_dict()` / `from_dict()` — serialization
  - `sample()` — draw a state from the distribution
  - `entropy()` — measure of behavioral uncertainty
  - `most_likely()` — dominant behavioral state
- [ ] P0.3 Create `tests/test_taxonomy.py` — validate taxonomy completeness
- [ ] P0.4 Create `tests/test_distribution.py` — KL-divergence math, blending correctness

### PHASE 1 — Schema and Config (Hours 1.5-2.5)
**Goal**: Behavioral profiles stored as proper distributions in YAML.

- [ ] P1.1 Update `config.py` — load/save v2 schema with BehavioralDistribution objects
- [ ] P1.2 Create default species-level `identity.yaml` (v2 schema, balanced distributions)
- [ ] P1.3 Create example domain personas: `developer.yaml`, `researcher.yaml`, `writer.yaml`
- [ ] P1.4 Update `bootstrap.py` — bootstrap creates v2 schema directories and defaults
- [ ] P1.5 Create `tests/test_config_v2.py`

### PHASE 2 — Hierarchy and Inheritance (Hours 2.5-3.5)
**Goal**: 4-level identity hierarchy with KL-blend working correctly.

- [ ] P2.1 Create `hierarchy.py` — IdentityHierarchy class:
  - Loads chain: species → domain → user → session
  - Resolves merged profile at each level using KL-blend
  - Handles missing levels gracefully (skip, use parent)
- [ ] P2.2 Refactor `inheritance.py` — replace scalar weighted average with KL-blend
- [ ] P2.3 Create `renderer.py` — converts merged BehavioralProfile to system prompt text
  - Maps each dimension's most-likely state to natural language instructions
  - Includes confidence qualifiers based on distribution entropy
- [ ] P2.4 Create `tests/test_hierarchy.py` — test full chain resolution

### PHASE 3 — Observation Engine (Hours 3.5-5)
**Goal**: Helios can observe raw agent outputs and update observed distributions.

- [ ] P3.1 Create `observer.py` — BehavioralObserver class:
  - `observe(messages: list[dict])` — accepts conversation messages
  - `extract_structural(messages)` — response length, list rate, question rate, hedge rate, code rate
  - `extract_semantic(messages)` — classify intent per response (confident/hedging/etc)
  - `extract_decision_points(messages)` — identify acted-without-asking vs checked-first
  - `extract_user_signals(messages)` — detect re-prompts, corrections, acceptances
  - `update_observed(persona, signals)` — Bayesian update of observed distributions
- [ ] P3.2 Create `tests/test_observer.py` — unit tests with fixture message sets

### PHASE 4 — Drift Detection (Hours 5-5.5)
**Goal**: Helios detects when observed behavior diverges from declared profile.

- [ ] P4.1 Create `drift.py` — DriftDetector class:
  - `compute_drift(declared, observed)` — total KL divergence across all dimensions
  - `per_dimension_drift(declared, observed)` — breakdown by axis
  - `exceeds_threshold(drift_score, threshold=0.30)` — trigger check
  - `drift_history` — time series of drift scores per persona
- [ ] P4.2 Update git commit schema to include drift score in commit metadata
- [ ] P4.3 Create `tests/test_drift.py`

### PHASE 5 — Negotiation Engine (Hours 5.5-6.5)
**Goal**: When drift crosses threshold, Helios generates a natural language summary and proposal.

- [ ] P5.1 Create `negotiation.py` — NegotiationEngine class:
  - `generate_summary(declared, observed, drift_by_dim)` → natural language paragraph
  - `generate_proposal(declared, observed)` → dict of proposed distribution updates
  - `apply_update(persona, accepted_changes)` → writes updated YAML + git commits
  - `reject_update(persona, reason)` → logs rejection, resets observation count
- [ ] P5.2 Add negotiation MCP tools to `server.py`:
  - `get_drift_report(persona_name)` → summary + drift scores
  - `negotiate_update(persona_name, decision, modified_values)` → apply or reject
- [ ] P5.3 Create `tests/test_negotiation.py`

### PHASE 6 — Harness and MCP Enhancement (Hours 6.5-7)
**Goal**: Complete delivery layer for Claude Code users.

- [ ] P6.1 Create `harness.py` — BehavioralHarness:
  - Python decorator `@behavioral_harness(persona='developer')`
  - Auto-injects rendered behavioral context
  - Auto-observes outputs after each call
  - Auto-triggers drift check after N interactions
- [ ] P6.2 Update `server.py` — new MCP tools:
  - `get_behavioral_context(persona_name)` → full system prompt text for injection
  - `observe_interaction(persona_name, messages)` → update observed distributions
- [ ] P6.3 Update CLI in `cli.py` — helios-mcp status, helios-mcp negotiate
- [ ] P6.4 Write Claude Code integration example in `docs/claude_code_integration.md`
- [ ] P6.5 Final test run: `uv run pytest tests/ -x` must pass 100%

---

## Loop Iteration Protocol

Each iteration of the loop agent MUST:

1. Read this file (HELIOS_V2_PLAN.md) to find the current state
2. Find the first unchecked task `[ ]` in order
3. Implement it fully — no stubs, no TODOs
4. Write tests for it
5. Run `uv run pytest tests/ -x --tb=short` and fix failures before moving on
6. Mark the task done `[x]` in this file
7. Commit with message format: `v2: [PHASE.TASK] description`
8. Move to the next task

**Rules**:
- Never skip a task to do a later one
- Never commit broken tests
- If a task takes more than one iteration, split it and note progress
- After each commit, update the "Last completed" line below

**Last completed**: (none yet — starting fresh)
**Current phase**: PHASE 0
**Tests passing**: baseline (run uv run pytest tests/ to check current count)

---

## Scientific Correctness Notes for Loop Agent

### KL-Divergence Formula
D_KL(P || Q) = sum_x P(x) * log(P(x) / Q(x))
- P is the "true" distribution (observed behavior)
- Q is the "model" distribution (declared profile)
- Result is always >= 0
- Result = 0 means P and Q are identical
- Handle log(0) with epsilon = 1e-10

### KL-Divergence Minimizing Blend
Given P (base) and Q (persona) with blend weight w:
The KL-minimizing mixture is: M(x) = w * P(x) + (1-w) * Q(x)
This IS the weighted mixture of distributions (Proposition 2 in mixture model theory).
The KL-divergence minimum over convex combinations is achieved at this mixture.
Weight w is computed from: w = base_importance / (specialization_level ** 2) — same formula, now applied to distributions.

### Drift Threshold
Default threshold: 0.30 total KL-divergence across all 4 dimensions.
Per-dimension threshold: 0.10 (flag individual dimension drift early).
Observation minimum: require at least 20 observations before computing drift.

### Distribution Validation
Every distribution must:
- Sum to 1.0 (within epsilon=1e-6)
- Have all non-negative values
- Have all states be valid taxonomy states for that dimension

---

## Delivery Summary for Claude Code Users

User installs helios-mcp (uvx or pip).
User adds to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "helios": { "command": "uvx", "args": ["helios-mcp"] }
  },
  "hooks": {
    "PreToolUse": [{
      "matcher": {},
      "hooks": [{"type": "command", "command": "helios-mcp hook pre-tool"}]
    }],
    "PostToolUse": [{
      "matcher": {},
      "hooks": [{"type": "command", "command": "helios-mcp hook post-tool"}]
    }]
  }
}
```

At session start: Claude Code calls `get_behavioral_context('developer')` → injects into system prompt.
After each tool use: hook sends interaction data to observer.
When drift crosses threshold: `get_drift_report` returns NL summary → Claude surfaces it to user.
User negotiates via `negotiate_update` tool → git commits the evolution.

The agent's behavioral biography lives in `~/.helios/` versioned by git.
