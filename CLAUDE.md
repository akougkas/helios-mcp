# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Helios

The behavioral genome for AI agents. Observes actual behavior, detects drift via a Dirichlet posterior and Jensen-Shannon divergence, negotiates profile updates with the human. Every change is git-committed. Ships as a Claude Code plugin (hooks + skills + MCP).

Not a RAG system, not a preference store, not a static personality file.

## Commands

```bash
uv sync                                    # install deps
uv run pytest tests/ -q                    # all tests (598)
uv run pytest tests/test_distribution.py   # single file
uv run pytest -k "js_is_symmetric"         # by name
uv run pytest --cov=src/helios_mcp         # coverage
uv run ruff check src/ tests/              # lint
uv run mypy src/helios_mcp/                # types
uv build --wheel                           # build
uv run helios-mcp                          # start MCP server
uv run helios-mcp init                     # onboard: import CLAUDE.md + output style, set default persona
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

The plugin's hooks capture derived features only (never prompt or tool content) and feed a per-turn heuristic classifier plus, at session end, a batch Haiku labeler. Both write soft labels over 9 behavioral dimensions into an append-only ledger. The estimator turns that ledger into a Dirichlet posterior per dimension and measures Jensen-Shannon divergence against the declared profile; see "Key Thresholds" below for the exact math. Human accepts or rejects each proposal. Accepted changes are YAML-written and git-committed.

### Identity Hierarchy

```
species (base/identity.yaml)           weight = base_importance / (specialization_level²)
  └→ domain (personas/developer.yaml)  M(x) = w·P_parent(x) + (1-w)·P_child(x)
       └→ user (personas/dev_user.yaml)
            └→ session (temporary/dev.yaml)
```

### Behavioral Dimensions

Stance (the original four):

| Dimension | States |
|-----------|--------|
| epistemic_style | confident, hedging, admits_ignorance, speculating |
| interaction_agency | asks_first, assumes_and_acts, offers_options, decides_unilaterally, defers_to_user |
| communication_register | terse, moderate, thorough, technical_dense, plain_accessible |
| risk_caution | acts_immediately, checks_before_acting, warns_frequently, refuses_ambiguity |

Manner (orthogonal to stance, added in round 4):

| Dimension | States |
|-----------|--------|
| structure | prose, light_structure, heavy_structure |
| sycophancy | candid, neutral, flattering |
| narration | silent_action, brief_signposting, narrates_and_recaps |
| specificity | concrete, mixed, vague |
| pushback | holds_position, concedes_with_reason, capitulates (labeled only when the user pushed back) |

Each dimension is a probability distribution over its states. Not labels, not scalars.

Taxonomy is **not locked**. Research needed before hardening (see `.specs/helios-vision-2026-03-11.md`).

### Module Flow

```
capture (plugin, stdlib only)          ingest (transcript -> ledger)              estimate / negotiate / serve
helios-plugin/hooks/hook-handler.py -> transcript.py -> AgentTurn/UserInput   ->  store.py: ObservationStore, ProposalStore
  derived features only, no content     classify.py (heuristic labels)             estimator.py -> drift.py (Dirichlet + JS)
                                         llm.py (Haiku batch labeler)                     |
                                         endorsement.py (judges the next user turn)       v
                                         ingest.py: ingest_session() appends to store  negotiation.py -> hierarchy.py -> profile.py
                                                                                            |                    |
                                                                                     renderer.py           distribution.py
                                                                                            |                    |
                                                                                    rendered/<persona>.md   taxonomy.py

service.py (HeliosService, the one engine API) wires store/estimator/drift/negotiation/hierarchy/renderer
├── server.py   (7 MCP tools, thin layer over service.py)
├── cli.py      (thin layer over service.py; `init` calls onboard.py, `ingest` calls ingest.py)
├── onboard.py  → importer.py → projector.py, llm.py   (declared_sources: CLAUDE.md + active output style)
├── exporter.py (yaml/json/soulspec)
├── bootstrap.py (default_profiles/ -> ~/.helios on first run)
├── atomic_ops.py (atomic YAML/text writes, git_commit)
└── security.py (validate_persona_name, persona_path; the path-traversal guard used everywhere personas are named)
```

`distribution.py` and `taxonomy.py` are the foundation. No circular imports. `calibrate.py` and `harness.py` are offline tooling, not on the runtime path.

### Key Thresholds

All live in `drift.DriftConfig`. Drift runs on the `endorsed` posterior only. With model labeling on, endorsed counts only turns that have an llm label; heuristic-only turns feed the fingerprint. With `HELIOS_LLM=0`, heuristic labels are authoritative.

- Posterior per dimension: `Dirichlet(s * declared + counts)`, prior strength s = 25 turns
- Evidence per turn: soft label * confidence ** 0.5, times the response grade for uncorrected turns: explicit approval (endorsement >= 0.75) 1.0, moved on (>= 0.25) 0.2, no response or an outcome complaint 0. Only endorsement <= -0.75 is a behavior correction
- Drift score: JS divergence (nats, at most ln 2) between posterior mean and declared
- Tiers over 1000 seeded samples of P(JS(sample, declared) > 0.0125): a suggestion at >= 0.8, a strong proposal at >= 0.95
- Auto-accept (silent): P(JS < 0.0125) >= 0.9 and JS(mean, declared) >= 0.004
- Standing preference (hint on an uncorrected turn): weight 1.0 toward the hinted state
- Declared dimensions (the ones `init`/`import` took from CLAUDE.md or the output style, recorded as `declared_dimensions` on the profile): uncorrected turns count toward endorsed only when explicitly approved; corrections, hints, standing preferences and rejections count as elsewhere, and the fingerprint is unaffected
- Unhinted correction: 0.25 weight spread over the complement of the label
- Rejection: 10 pseudo-counts toward the declared profile, 3-day cooldown per dimension
- Probability floor on disk and in priors: 0.005
- Simulated with hard labels on the default profiles, every turn an approval, checking every turn: strong-tier stationary FP < 1% over 200 turns (under 0.3% by turn 30); a 0.3-mass shift is detected at a median of 26 to 30 turns (80th percentile 38 to 44)
- Founder corpus, 200 model-labeled sessions (600 turns, 16 approvals, 99 hints, 75 corrections), 100 random session orders: stationary FP 2% for suggestions and 0% for strong proposals (23% for suggestions at 0.7, 98% at s = 15). Against the default developer profile, interaction_agency becomes a suggestion after session 59 and strong after session 122, and communication_register a suggestion after session 139. Without response grading the same corpus proposes agency after session 3, so explicit signals set the pace; the moved-on weight barely matters (0.1 to 0.3 gives sessions 59 to 61)

## Design Constraints

1. **Observe only, never steer.** Helios never blocks or modifies agent behavior in real-time. This is required for Anthropic plugin verification.
2. **UV only.** Never pip.
3. **Zero attribution.** No AI/Claude/Anthropic mentions in code or commits.
4. **Constitutional layering.** Helios personalizes above the AI's safety constitution. Never contradicts it.
5. **Personalization framing.** Public messaging leads with "learn your preferences," not "detect laziness." Drift detection is mechanism, not headline.

## Current Roadmap

Done: hook-based observation, heuristic + Haiku labeling, the nine-dimension taxonomy, Dirichlet/JS drift with suggestion/strong tiers, negotiation and auto-accept, declared-artifact import (CLAUDE.md + active output style), and plugin packaging (hooks + skill + MCP bundle).

Open:

1. Per-model fingerprinting: track the agent's tendencies per model and render a short counter-tendency block where a model's fingerprint deviates from the endorsed preference.
2. Ledger scaling for long-running personas (index or partition the JSONL ledger so a Stop hook stays cheap as it grows).
3. Local dogfooding on the founder's real sessions, watching for false positives and proposal pacing.
4. Distribution: Anthropic marketplace submission, PyPI, standalone skill.

## Reference

- `.specs/helios-vision-2026-03-11.md`: full project spec from founder interview
