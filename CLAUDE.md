# CLAUDE.md — Helios MCP

## What This Is

Helios is a behavioral science system for AI agents. It observes how an agent actually behaves, detects drift from its declared personality, and negotiates profile updates with the human. The agent's behavioral biography lives in `~/.helios/` versioned by git.

**Not** a RAG system, not a preference store, not a knowledge base.

## Current State (v0.3.0)

5 MCP tools, 253 tests passing, clean codebase (~3,900 lines source).

### Tools
1. `list_personas` — discover available persona names
2. `get_behavioral_context` — resolve 4-level hierarchy, render as system prompt
3. `observe_interaction` — feed conversation messages into the observation engine
4. `get_drift_report` — natural language summary of behavioral drift
5. `negotiate_update` — accept or reject proposed profile changes (git-committed)

### Core Science
- **4 behavioral dimensions**: epistemic style, interaction agency, communication register, risk/caution
- **Probability distributions** over discrete states (not scalars)
- **KL-divergence** for drift detection and blending
- **4-level hierarchy**: species → domain → user → session
- **Inheritance formula**: `weight = base_importance / (specialization_level²)`
- **Blending**: `M(x) = w * P_base(x) + (1-w) * P_persona(x)`

### File Layout
```
~/.helios/
├── base/          # Species-level identity (identity.yaml)
├── personas/      # Domain personas (developer.yaml, researcher.yaml, ...)
├── learned/       # Reserved for future use
├── temporary/     # Session-level overrides
└── observations/  # Persisted observation data (JSON)
```

## Tech Stack

- **Python 3.13** with UV exclusively (`uv run`, `uv sync`, `uv build`)
- **FastMCP 2.2.6+** — `@mcp.tool` decorators
- **PyYAML** — behavioral profile serialization
- **GitPython** — behavioral biography versioning
- **Click** — CLI interface

## Source Modules

| Module | Purpose |
|--------|---------|
| `server.py` | 5 MCP tools — the public API |
| `taxonomy.py` | 4 dimensions, their states, validation |
| `distribution.py` | BehavioralDistribution, KL-divergence, blending |
| `profile.py` | BehavioralProfile dataclass, load/save YAML |
| `hierarchy.py` | 4-level identity resolution with KL-blend |
| `observer.py` | Signal extraction from conversations |
| `drift.py` | KL-divergence threshold detection |
| `negotiation.py` | Natural language summaries, git-committed updates |
| `renderer.py` | Profile → system prompt text |
| `harness.py` | Python decorator for wrapping agents |
| `inheritance.py` | `kl_blend_profiles()` standalone function |
| `cli.py` | Click CLI: `helios-mcp`, `helios-mcp status`, `helios-mcp negotiate` |
| `bootstrap.py` | First-run directory setup and default profiles |
| `config.py` | HeliosConfig dataclass, ConfigLoader |
| `git_store.py` | Git repository operations |
| `security.py` | Input validation, path traversal prevention |
| `atomic_ops.py` | `atomic_write_yaml()` — temp file + rename |

## Development Rules

1. **UV only** — never pip
2. **No over-engineering** — this codebase was cleaned from 8k to 4k lines for a reason
3. **Tests must pass** — `uv run pytest tests/ -q` (253 tests)
4. **Zero attribution** — no AI/Claude/Anthropic mentions in code or commits
5. **Edit minimally** — prefer editing existing files over creating new ones
6. **Build verifies** — `uv build --wheel` must succeed

## User Setup

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "helios": { "command": "uvx", "args": ["helios-mcp"] }
  }
}
```

## Key Reference

- `HELIOS_V2_PLAN.md` — full architecture plan and scientific notes
- `docs/claude_code_integration.md` — user integration guide
- `docs/planning/` — original PRD and plan
- `docs/samples/` — example YAML configurations
