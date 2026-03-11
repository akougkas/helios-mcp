# Helios v2 — Claude Code Integration Guide

## What This Does

Helios gives your Claude Code agent a persistent behavioral identity that evolves through use. Instead of starting each session from scratch, your agent carries consistent behavioral patterns — how confident it is, how it communicates, how cautious it is — that adapt over time based on what actually works.

Each session, Helios injects a behavioral profile as a system prompt section. Over time, the observer compares what the agent actually does against what the profile declares. When the gap grows large enough, Helios asks you whether to keep the drift (accepting the evolved behavior) or revert to the declared profile.

## Quick Setup (5 minutes)

### 1. Install Helios

```bash
uvx helios-mcp init
```

This creates `~/.helios/` with default behavioral profiles for the developer, researcher, and writer personas.

### 2. Add to Claude Code settings

In your project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "helios": {
      "command": "uvx",
      "args": ["helios-mcp"]
    }
  }
}
```

Restart Claude Code after saving.

### 3. Use behavioral context in your sessions

At the start of a session, call the MCP tools in order:

1. `get_behavioral_context("developer")` — injects the behavioral profile as system context
2. After work: `observe_interaction("developer", messages)` — records what actually happened
3. Check for drift: `get_drift_report("developer")` — natural language drift summary
4. Accept or reject evolution: `negotiate_update("developer", "accept")` — commits behavioral growth

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_base_config` | Load the foundation configuration that all personas inherit from |
| `get_active_persona` | Retrieve a persona with its full specialization and inheritance chain applied |
| `merge_behaviors` | Run the weighted inheritance calculation between two profiles |
| `list_personas` | Discover all available personas in your Helios directory |
| `update_preference` | Modify a configuration value directly in a persona YAML file |
| `search_patterns` | Search for behavioral patterns across all personas |
| `commit_changes` | Persist the current state of a persona to git with a semantic commit message |
| `learn_behavior` | Add or update a behavioral key-value pair in a persona |
| `tune_weight` | Adjust `specialization_level` or `base_importance` to change inheritance strength |
| `revert_learning` | Undo recent behavioral changes by reverting git commits |
| `evolve_behavior` | Promote a behavior from a persona up to the base config, or between personas |

## The Behavioral Dimensions

Helios tracks four behavioral dimensions for each persona:

**epistemic_style** — how the agent handles uncertainty. States: `confident`, `hedging`, `admits_ignorance`, `speculating`. A confident agent states things directly; a hedging agent qualifies claims frequently.

**interaction_agency** — how autonomous the agent is. States: `asks_first`, `assumes_and_acts`, `offers_options`, `decides_unilaterally`, `defers_to_user`. A developer persona often defaults to `assumes_and_acts`; a research persona may prefer `asks_first`.

**communication_register** — the structure and density of outputs. States: `terse`, `moderate`, `thorough`, `technical_dense`, `plain_accessible`. Affects response length and vocabulary complexity.

**risk_caution** — how the agent weighs safety versus speed. States: `acts_immediately`, `checks_before_acting`, `warns_frequently`, `refuses_ambiguity`. Higher caution means more confirmations and warnings before consequential actions.

Each dimension is represented as a probability distribution over its states, not a single label. This allows nuanced behavior — an agent that is mostly `confident` but occasionally `hedging` is different from one that is uniformly distributed.

## Understanding Drift

Drift measures how far the agent's actual behavior has moved from its declared profile. Helios uses KL-divergence (a scientifically grounded information-theoretic measure) to quantify this per dimension and in total.

**When drift triggers:** After at least 20 observations, if the total KL-divergence across all four dimensions exceeds 0.30, Helios flags the persona as drifting.

**What the negotiation looks like:** The CLI shows a per-dimension breakdown — which dimensions drifted, how much, and what the declared versus observed dominant states are. You then choose to accept (updating the declared profile to match observed behavior) or reject (keeping the declared profile as-is).

**Why this matters:** Without drift detection, a persona silently diverges from its declared identity. With negotiation, behavioral evolution is explicit and reversible — every change is a git commit.

## Checking Your Profile

```bash
helios-mcp status
```

Shows the current behavioral profile for all personas, including the dominant state and entropy level for each dimension. High entropy means the profile is uncertain across states; low entropy means it is concentrated on one dominant behavior.

```bash
helios-mcp negotiate developer
```

Runs an interactive drift report for the developer persona. If there are no observations yet, it reports that. If drift is detected, it shows the per-dimension breakdown and prompts for action.

## Using the Python Harness

For Python-based agents, the `BehavioralHarness` class provides decorator and context manager interfaces:

```python
from helios_mcp.harness import BehavioralHarness

harness = BehavioralHarness(persona="developer")

@harness
def my_agent(messages: list[dict], system: str = "") -> str:
    return call_llm(messages, system=system)

result = my_agent(messages)
```

The harness automatically injects the rendered behavioral profile into the `system` parameter and records the output for drift tracking.

As a context manager:

```python
with BehavioralHarness(persona="developer") as h:
    context = h.get_context()
    response = call_llm(messages, system=context)
    h.observe(messages + [{"role": "assistant", "content": response}])

    if h.should_negotiate():
        print(h.get_drift_summary())
```

## File Structure

Helios stores all configuration in `~/.helios/`:

```
~/.helios/
├── base/
│   └── identity.yaml      # Species-level base profile inherited by all personas
├── personas/
│   ├── developer.yaml     # Developer persona with specialization_level and base_importance
│   ├── researcher.yaml
│   └── writer.yaml
├── learned/               # Learned patterns (managed by learn_behavior tool)
└── temporary/             # Session-scoped overrides (cleared on session end)
```

All changes are versioned with git. Every `learn_behavior`, `tune_weight`, and `evolve_behavior` call creates a semantic commit message so you can see exactly how the personality evolved over time.
