# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Helios

The behavioral genome for AI agents. Observes actual behavior, detects drift via KL-divergence, negotiates profile updates with the human. Every change is git-committed. Ships as a Claude Code plugin (hooks + skills + MCP).

Not a RAG system, not a preference store, not a static personality file.

## Commands

```bash
uv sync                                    # install deps
uv run pytest tests/ -q                    # all tests (253)
uv run pytest tests/test_distribution.py   # single file
uv run pytest -k "kl_divergence"           # by name
uv run pytest --cov=src/helios_mcp         # coverage
uv run ruff check src/ tests/              # lint
uv run mypy src/helios_mcp/                # types
uv build --wheel                           # build
uv run helios-mcp                          # start MCP server
uv run helios-mcp status                   # show profiles
uv run helios-mcp negotiate <persona>      # drift report
```

## Architecture

### The Cycle

```
observe_interaction → get_drift_report → negotiate_update → git commit
        ↑                                        |
        └────────────── next session ────────────┘
```

Hook events (PreToolUse, PostToolUse, SubagentStart/Stop, Notification, etc.) feed the observer. The observer accumulates signals into probability distributions over 4 behavioral dimensions. When KL-divergence between observed and declared exceeds 0.30 total (or 0.10 per dimension, minimum 20 observations), negotiation is recommended. Human accepts or rejects. Accepted changes are YAML-written and git-committed.

### Identity Hierarchy

```
species (base/identity.yaml)           weight = base_importance / (specialization_level²)
  └→ domain (personas/developer.yaml)  M(x) = w·P_parent(x) + (1-w)·P_child(x)
       └→ user (personas/dev_user.yaml)
            └→ session (temporary/dev.yaml)
```

### Behavioral Dimensions

| Dimension | States |
|-----------|--------|
| epistemic_style | confident, hedging, admits_ignorance, speculating |
| interaction_agency | asks_first, assumes_and_acts, offers_options, decides_unilaterally, defers_to_user |
| communication_register | terse, moderate, thorough, technical_dense, plain_accessible |
| risk_caution | acts_immediately, checks_before_acting, warns_frequently, refuses_ambiguity |

Each dimension is a probability distribution over its states. Not labels, not scalars.

Taxonomy is **not locked**. Research needed before hardening (see `.specs/helios-vision-2026-03-11.md`).

### Module Flow

```
server.py (5 MCP tools)
├── hierarchy.py → profile.py → distribution.py → taxonomy.py
├── observer.py → distribution.py, taxonomy.py
├── drift.py → distribution.py
├── negotiation.py → drift.py, observer.py, profile.py
├── renderer.py → profile.py, taxonomy.py
└── security.py
```

`distribution.py` and `taxonomy.py` are the foundation. No circular imports.

### Key Thresholds

- Total drift trigger: 0.30
- Per-dimension trigger: 0.10
- Auto-accept threshold: KL < 0.05 (silent)
- Minimum observations: 20

## Design Constraints

1. **Observe only, never steer.** Helios never blocks or modifies agent behavior in real-time. This is required for Anthropic plugin verification.
2. **UV only.** Never pip.
3. **Zero attribution.** No AI/Claude/Anthropic mentions in code or commits.
4. **Constitutional layering.** Helios personalizes above the AI's safety constitution. Never contradicts it.
5. **Personalization framing.** Public messaging leads with "learn your preferences," not "detect laziness." Drift detection is mechanism, not headline.

## Current Roadmap

1. Observation overhaul (hook events, not just text signals)
2. Profile import engine (CLAUDE.md/soul.md → distributions via LLM parsing)
3. Claude Code plugin packaging (hooks + skills + MCP bundle)
4. Local dogfooding
5. Distribution: Anthropic marketplace (verified), PyPI, standalone skill

## Reference

- `.specs/helios-vision-2026-03-11.md` — full project spec from founder interview
- `HELIOS_V2_PLAN.md` — implementation plan and scientific notes
- `docs/claude_code_integration.md` — user integration guide
