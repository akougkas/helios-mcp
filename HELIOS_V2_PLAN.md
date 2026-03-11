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

- [x] P0.1 Create `taxonomy.py` — BEHAVIORAL_TAXONOMY dict, validate_state(), list_dimensions()
- [x] P0.2 Create `distribution.py` — BehavioralDistribution class with:
  - `__init__(dimension, states_dict)` — validates sums to 1.0
  - `kl_divergence(other)` — D_KL(self || other)
  - `kl_blend(other, weight)` — KL-divergence minimizing mixture
  - `to_dict()` / `from_dict()` — serialization
  - `sample()` — draw a state from the distribution
  - `entropy()` — measure of behavioral uncertainty
  - `most_likely()` — dominant behavioral state
- [x] P0.3 Create `tests/test_taxonomy.py` — validate taxonomy completeness
- [x] P0.4 Create `tests/test_distribution.py` — KL-divergence math, blending correctness

### PHASE 1 — Schema and Config (Hours 1.5-2.5)
**Goal**: Behavioral profiles stored as proper distributions in YAML.

- [x] P1.1 Create `profile.py` — BehavioralProfile dataclass with v2 schema, load/save, default_species()
- [x] P1.2 Create default species-level `identity.yaml` (v2 schema, balanced distributions)
- [x] P1.3 Create domain personas: `developer.yaml`, `researcher.yaml`, `writer.yaml` in default_profiles/
- [x] P1.4 Update `bootstrap.py` — bootstrap creates v2 schema directories and defaults
- [x] P1.5 Create `tests/test_profile.py` — 23 tests passing

### PHASE 2 — Hierarchy and Inheritance (Hours 2.5-3.5)
**Goal**: 4-level identity hierarchy with KL-blend working correctly.

- [x] P2.1 Create `hierarchy.py` — IdentityHierarchy resolves species→domain→user→session chain
- [x] P2.2 Update `inheritance.py` — added kl_blend_profiles() alongside existing scalar blend
- [x] P2.3 Create `renderer.py` — BehavioralRenderer converts profile to system prompt text
- [x] P2.4 Create `tests/test_hierarchy.py` + `tests/test_renderer.py` — all passing

### PHASE 3 — Observation Engine (Hours 3.5-5)
**Goal**: Helios can observe raw agent outputs and update observed distributions.

- [x] P3.1 Create `observer.py` — BehavioralObserver with 4 signal extractors + signals_to_distributions
- [x] P3.2 Create `tests/test_observer.py` — 44 tests passing

### PHASE 4 — Drift Detection (Hours 5-5.5)
**Goal**: Helios detects when observed behavior diverges from declared profile.

- [x] P4.1 Create `drift.py` — DriftDetector with DriftResult, thresholds, history, trend analysis
- [x] P4.2 Git commit messages include drift info (in negotiation.py apply_update)
- [x] P4.3 Create `tests/test_drift.py` — 40 tests passing

### PHASE 5 — Negotiation Engine (Hours 5.5-6.5)
**Goal**: When drift crosses threshold, Helios generates a natural language summary and proposal.

- [x] P5.1 Create `negotiation.py` — NegotiationEngine with NegotiationProposal, generate_summary, apply_update, reject_update
- [x] P5.2 Add to `server.py`: get_drift_report, negotiate_update MCP tools
- [x] P5.3 Create `tests/test_negotiation.py` — 22 tests passing

### PHASE 6 — Harness and MCP Enhancement (Hours 6.5-7)
**Goal**: Complete delivery layer for Claude Code users.

- [x] P6.1 Create `harness.py` — BehavioralHarness decorator + context manager
- [x] P6.2 Update `server.py` — get_behavioral_context, observe_interaction v2 MCP tools
- [x] P6.3 Update `cli.py` — helios-mcp status, helios-mcp negotiate subcommands
- [x] P6.4 Create `docs/claude_code_integration.md`
- [x] P6.5 Final test suite: 252 v2 tests passing

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

**Last completed**: P6.5 — ALL PHASES COMPLETE — 252 v2 tests passing
**Current phase**: COMPLETE ✅
**Tests passing**: 252 v2 tests (all phases)

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
