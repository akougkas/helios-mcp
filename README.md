# Helios MCP

**A behavioral genome for AI agents.** Helios is a Model Context Protocol (MCP)
server that represents an agent's personality as probability distributions,
measures how far observed behavior drifts from the declared profile using a
Dirichlet posterior and Jensen-Shannon divergence, and asks before committing
a change.

[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/akougkas/helios-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/akougkas/helios-mcp/actions/workflows/ci.yml)
[![Built with UV](https://img.shields.io/badge/built%20with-UV-blue?logo=python)](https://github.com/astral-sh/uv)

## The problem

Every AI conversation starts from zero. You re-explain how you like to work,
your AI has no memory of your preferences, and there is no principled way to
say "this agent's behavior has drifted from what I asked for." That's because
"behavior" is usually just prose in a `CLAUDE.md` file, not something you can
measure.

## The model

Helios represents behavior along nine fixed dimensions, defined in
[`src/helios_mcp/taxonomy.py`](src/helios_mcp/taxonomy.py). Four cover stance:

| Dimension | What it captures | States |
|---|---|---|
| `epistemic_style` | how the agent handles uncertainty | confident, hedging, admits_ignorance, speculating |
| `interaction_agency` | how autonomously it acts | asks_first, assumes_and_acts, offers_options, decides_unilaterally, defers_to_user |
| `communication_register` | formality and density of output | terse, moderate, thorough, technical_dense, plain_accessible |
| `risk_caution` | how it weighs safety vs. speed | acts_immediately, checks_before_acting, warns_frequently, refuses_ambiguity |

Five more, orthogonal to stance, cover manner:

| Dimension | What it captures | States |
|---|---|---|
| `structure` | prose versus headers and bullets | prose, light_structure, heavy_structure |
| `sycophancy` | praise and validation versus candor | candid, neutral, flattering |
| `narration` | announcing, recapping, closing pleasantries | silent_action, brief_signposting, narrates_and_recaps |
| `specificity` | concrete references versus adjectives | concrete, mixed, vague |
| `pushback` | holding a position versus giving in (labeled only when the user pushed back) | holds_position, concedes_with_reason, capitulates |

Each dimension is not a label or a scalar. It's a `BehavioralDistribution`
([`distribution.py`](src/helios_mcp/distribution.py)): a probability over
that dimension's discrete states, always summing to 1.0. A persona that is
"mostly terse but sometimes thorough" is `{terse: 0.6, thorough: 0.3, ...}`,
not a single string.

Helios keeps two such distributions per dimension per persona: a `fingerprint`
(what the agent actually did, across every turn, diagnostics only) and an
`endorsed` posterior (the style the user endorses, built from a Dirichlet
prior centered on the declared profile plus evidence from observed turns,
weighted up for explicit signals like corrections and standing preferences
and down for a turn the user just moved past). Drift and negotiation run on
`endorsed` only. Measuring the gap as **Jensen-Shannon divergence** between
the posterior mean and the declared profile gives a single comparable number
per dimension, symmetric and bounded by `ln 2`, which is what `drift.py` and
`negotiation.py` need to decide whether behavior has actually changed or is
just noise, and whether a proposal is a mild suggestion or a strong one.

### Identity hierarchy

Profiles resolve through four levels: species, domain, user, session
(`IdentityHierarchy` in [`hierarchy.py`](src/helios_mcp/hierarchy.py)).
A species-level base blends with an optional domain persona, then an
optional per-user adaptation, then an optional per-session override. Each
blend step is a mixture, `M(x) = w · parent(x) + (1-w) · child(x)`, where the
weight is:

```
weight = parent.base_importance / (child.specialization_level ** 2)
```

Higher `base_importance` or lower `specialization_level` pulls the result
toward the parent; a highly specialized child dominates.

### Drift and negotiation

[`drift.py`](src/helios_mcp/drift.py) measures, per dimension, the Jensen-Shannon
divergence between the endorsed posterior mean and the declared profile, plus
a credibility check via seeded Dirichlet sampling. A dimension can surface as
a **suggestion** (lower credibility bar) or a **strong proposal** (higher bar),
phrased as suggestions either way so a plain "no" is a complete answer. A
small, well-supported move auto-accepts silently; a bigger one goes through
[`negotiation.py`](src/helios_mcp/negotiation.py), which persists a proposal
with an id, writes a natural-language summary, and waits. Nothing is written
until a human (or the calling agent, on the human's behalf) accepts it by that
id, at which point the target profile is written to the persona's user-level
YAML and committed to git so every behavioral change has a history and can be
rolled back. A rejection is recorded too, with a cooldown per dimension so a
declined proposal doesn't re-fire immediately.

Explicit signals move faster than passive ones. A correction that names what
you want, or a standing preference stated on an uncorrected turn, weighs 2.5
turns against the usual one, so a handful of consistent hints on a dimension
reaches a suggestion in about 5 and a strong proposal in about 7, without
waiting on volume alone. And a dimension that `init` or `import` took directly
from a declared source (`CLAUDE.md`, the active output style, recorded as
`declared_dimensions` on the profile) only moves on those same explicit
signals: an uncorrected turn that merely matches or drifts from a declared
dimension carries no endorsed weight there, so passing on Helios's own
rendered suggestion can't quietly outvote what you wrote down yourself.
`status` marks these dimensions `declared: explicit signals only`. Exact
thresholds live in `drift.DriftConfig` and are documented in
[`CLAUDE.md`](CLAUDE.md#key-thresholds).

## MCP tools

The server ([`src/helios_mcp/server.py`](src/helios_mcp/server.py)) exposes
exactly **7 tools**, all registered with `@mcp.tool`:

| Tool | Parameters | What it does |
|---|---|---|
| `list_personas` | — | Lists persona names found under `~/.helios/personas/*.yaml`. |
| `get_behavioral_context` | `persona_name` | Resolves the 4-level hierarchy for the persona and renders it as system-prompt text. |
| `observe_interaction` | `persona_name`, `messages`, `session_id` | Turns conversation messages into observations, appends them to the persona's ledger, and reports current drift and whether negotiation is recommended. |
| `get_drift_report` | `persona_name` | Computes endorsed drift against the declared profile: a natural-language summary, per-dimension detail, fingerprint diagnostics, and the id of any pending proposal with its tier (suggestion/strong). |
| `negotiate_update` | `proposal_id`, `decision` (`accept`/`reject`), `persona_name`, `reason`, `accepted_dimensions` | Accepts a proposal by id (writes the persona's user-level YAML and git-commits it) or records a rejection with a per-dimension cooldown. |
| `import_profile` | `source_path`, `persona_name` | Parses a personality file (e.g. `CLAUDE.md`) and creates a new persona with projected distributions. |
| `export_profile` | `persona_name`, `format` (`yaml`/`json`/`soulspec`), `dimensions` | Exports a resolved profile, optionally filtered to specific dimensions. |

## Delivery

Helios ships on three surfaces:

- **Claude Code plugin**: [`helios-plugin/`](helios-plugin/) bundles the
  MCP server config (`.mcp.json`), observation hooks (`hooks/`), a skill
  (`skills/helios/SKILL.md`), and an observer agent (`agents/`).
- **Standalone skill**: [`helios-skill/`](helios-skill/) has just the MCP
  config and `SKILL.md`, for lighter-weight adoption without the hooks.
- **Marketplace entry**: [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)
  lists `helios-plugin/` as an installable plugin. The manifest lives at the
  repo root, not in a nested `marketplace/` directory, because a marketplace
  plugin `source` must resolve inside the marketplace's own root. A source
  pointing anywhere outside that root, symlink or plain relative path, is
  rejected at install.

The package also installs a console script: `helios-mcp = helios_mcp.cli:main`.

## Install and run

Requires Python ≥ 3.13, managed with [uv](https://docs.astral.sh/uv/). Not on
PyPI yet, so install from a local checkout.

```bash
git clone https://github.com/akougkas/helios-mcp
cd helios-mcp
uv sync
uv run helios-mcp --verbose   # starts the MCP server over stdio
uv run helios-mcp init        # onboard: import CLAUDE.md + the active output style
```

On first run, `helios-mcp` bootstraps `~/.helios/` (or `$HELIOS_DIR`): it
creates `base/`, `personas/`, `learned/`, `temporary/`, initializes a git
repo there, and copies the default species profile and `developer`/
`researcher`/`writer` domain personas. `helios-mcp init` goes further: it
imports the active `CLAUDE.md` and output style into a persona's user level
as the authoritative starting profile and sets it as the default.

Both delivery surfaces below ship a `.mcp.json` that resolves the server via
`uvx --from "${HELIOS_SOURCE:-helios-mcp}" helios-mcp`. Point `HELIOS_SOURCE`
at a local checkout to use it before it's published:

```bash
export HELIOS_SOURCE=/path/to/helios-mcp
```

### CLI

Beyond running the server, `helios-mcp` has subcommands:

```bash
uv run helios-mcp init [persona] --home PATH --project-dir PATH
                                          # onboard: import CLAUDE.md + the active output
                                          # style into persona's user level, set default
uv run helios-mcp status                 # print resolved profiles, evidence, pending proposals
uv run helios-mcp negotiate <persona>    # show a drift report and accept/reject it
uv run helios-mcp persona default [name] # show, or set, the default persona
uv run helios-mcp render [persona]       # write rendered/<persona>.md (SessionStart context)
uv run helios-mcp export <persona> --format yaml|json|soulspec
uv run helios-mcp import <path> --persona NAME
uv run helios-mcp ingest --persona NAME --session-id ID --transcript PATH [--final]
                                          # internal: labels a transcript into the ledger, run by the plugin's hooks
```

### Environment variables

| Variable | Effect |
|---|---|
| `HELIOS_DIR` | Where profiles, the ledger and proposals live. Default `~/.helios`. |
| `HELIOS_SOURCE` | Local checkout path for `uvx --from`, so the plugin's `.mcp.json` can run an unpublished build. |
| `HELIOS_LLM` | Set to `0` to skip the Haiku batch labeler; heuristic labels stay authoritative. Same as `llm: false` in `HELIOS_DIR/config.yaml`. |
| `HELIOS_PERSONA` | Overrides persona resolution in the plugin's hooks, ahead of a `.helios-persona` file or the stored default. |
| `HELIOS_DISABLE` | Set to `1` to make every hook and the Haiku subprocess a no-op. The labeler subprocess sets this on itself so it never re-triggers Helios's own hooks. |
| `HELIOS_TRUST_HEADLESS` | Set to `1` to make a headless `claude -p` session's user turns count as the person's own feedback instead of machine input. For scripted lab sessions only; system, notification, peer, coordinator and scheduled input are still always treated as machine input regardless of this variable. |

## Project status

The behavioral math is solid: taxonomy, distributions, hierarchy blending,
Dirichlet/JS drift, and negotiation are implemented and covered by an
extensive test suite (see the [CI workflow](.github/workflows/ci.yml) for the
current pass/fail state, since a hardcoded count in prose goes stale). Hook
capture, transcript labeling, declared-artifact import, per-model fingerprint
tracking, and plugin packaging are wired end to end and have run against the
founder's own real session history. The package is at `0.5.0b1` and
classified as beta: it's not yet on PyPI or the Anthropic plugin marketplace,
and long-running, ongoing dogfooding is still open.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, running tests
(`uv run --frozen pytest`), linting (`uv run ruff check .`), type checking
(`uv run mypy src`), and pre-commit hooks.

## License

MIT © 2025 Anthony Kougkas. See [`LICENSE`](LICENSE).
