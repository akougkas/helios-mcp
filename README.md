# Helios MCP

**A behavioral genome for AI agents** — a Model Context Protocol (MCP) server that
represents an agent's personality as probability distributions, measures how far
observed behavior drifts from the declared profile using KL-divergence, and asks
before committing a change.

[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/akougkas/helios-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/akougkas/helios-mcp/actions/workflows/ci.yml)
[![Built with UV](https://img.shields.io/badge/built%20with-UV-blue?logo=python)](https://github.com/astral-sh/uv)

## The problem

Every AI conversation starts from zero. You re-explain how you like to work,
your AI has no memory of your preferences, and there is no principled way to
say "this agent's behavior has drifted from what I asked for" — because
"behavior" is usually just prose in a `CLAUDE.md` file, not something you can
measure.

## The model

Helios represents behavior along four fixed dimensions, defined in
[`src/helios_mcp/taxonomy.py`](src/helios_mcp/taxonomy.py):

| Dimension | What it captures | States |
|---|---|---|
| `epistemic_style` | how the agent handles uncertainty | confident, hedging, admits_ignorance, speculating |
| `interaction_agency` | how autonomously it acts | asks_first, assumes_and_acts, offers_options, decides_unilaterally, defers_to_user |
| `communication_register` | formality and density of output | terse, moderate, thorough, technical_dense, plain_accessible |
| `risk_caution` | how it weighs safety vs. speed | acts_immediately, checks_before_acting, warns_frequently, refuses_ambiguity |

Each dimension is not a label or a scalar — it's a `BehavioralDistribution`
([`distribution.py`](src/helios_mcp/distribution.py)): a probability over
that dimension's discrete states, always summing to 1.0. A persona that is
"mostly terse but sometimes thorough" is `{terse: 0.6, thorough: 0.3, ...}`,
not a single string.

Representing behavior this way makes **KL-divergence** the natural way to
measure drift: `D_KL(observed || declared) = Σ p(x) · log(p(x)/q(x))` is the
standard measure of how much information is lost when one distribution is
used to approximate another. It's always ≥ 0, it's 0 only when the two
distributions are identical, and — unlike a diff on free text — it gives a
single comparable number per dimension and an aggregate total, which is what
`DriftDetector` needs to decide whether behavior has actually changed or is
just noise.

### Identity hierarchy

Profiles resolve through four levels — species → domain → user → session
(`IdentityHierarchy` in [`hierarchy.py`](src/helios_mcp/hierarchy.py)):
a species-level base blends with an optional domain persona, then an
optional per-user adaptation, then an optional per-session override. Each
blend step is a **KL-minimizing mixture**, `M(x) = w · parent(x) + (1-w) · child(x)`,
where the weight comes from
[`inheritance.py`](src/helios_mcp/inheritance.py):

```
weight = base_importance / (specialization_level ** 2)
```

Higher `base_importance` or lower `specialization_level` pulls the result
toward the parent; a highly specialized child dominates.

### Drift and negotiation

[`drift.py`](src/helios_mcp/drift.py)'s `DriftDetector` sums per-dimension KL
divergence between what was observed and what's declared. Drift is only
actionable once there's enough signal: a minimum of **20 observations**, a
**per-dimension threshold of 0.10**, and a **total threshold of 0.30**. Below
`0.05` per dimension the change is small enough to consider auto-acceptable;
above the thresholds, [`negotiation.py`](src/helios_mcp/negotiation.py)'s
`NegotiationEngine` writes a natural-language summary of what changed and
proposes a concrete replacement profile. Nothing is written until a human (or
the calling agent, on the human's behalf) accepts it — `apply_update()` then
writes the persona YAML and commits it to git so every behavioral change has
a history and can be rolled back.

## MCP tools

The server ([`src/helios_mcp/server.py`](src/helios_mcp/server.py)) exposes
exactly **7 tools**, all registered with `@mcp.tool`:

| Tool | Parameters | What it does |
|---|---|---|
| `list_personas` | — | Lists persona names found under `~/.helios/personas/*.yaml`. |
| `get_behavioral_context` | `persona_name` | Resolves the 4-level hierarchy for the persona and renders it as system-prompt text. |
| `observe_interaction` | `persona_name`, `messages` | Feeds conversation messages into the observer, updates the accumulated distributions, and reports current drift and whether negotiation is recommended. |
| `get_drift_report` | `persona_name` | Computes drift against the declared profile and returns a natural-language summary plus per-dimension detail (requires prior observations). |
| `negotiate_update` | `persona_name`, `decision` (`accept`/`reject`), `reason`, `accepted_dimensions` | Applies an accepted drift proposal (writes the persona YAML and git-commits it) or records a rejection. |
| `import_profile` | `source_path`, `persona_name` | Parses a personality file (e.g. `CLAUDE.md`) and creates a new persona with projected distributions. |
| `export_profile` | `persona_name`, `format` (`yaml`/`json`/`soulspec`), `dimensions` | Exports a resolved profile, optionally filtered to specific dimensions. |

## Delivery

Helios ships on three surfaces:

- **Claude Code plugin** — [`helios-plugin/`](helios-plugin/): bundles the
  MCP server config (`.mcp.json`), observation hooks (`hooks/`), a skill
  (`skills/helios/SKILL.md`), and an observer agent (`agents/`).
- **Standalone skill** — [`helios-skill/`](helios-skill/): just the MCP
  config and `SKILL.md`, for lighter-weight adoption without the hooks.
- **Marketplace entry** — [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json):
  lists `helios-plugin/` as an installable plugin. The manifest lives at the
  repo root, not in a nested `marketplace/` directory, because a marketplace
  plugin `source` must resolve inside the marketplace's own root. A source
  pointing anywhere outside that root, symlink or plain relative path, is
  rejected at install.

The package also installs a console script: `helios-mcp = helios_mcp.cli:main`.

## Install and run

Requires Python ≥ 3.13, managed with [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/akougkas/helios-mcp
cd helios-mcp
uv sync
uv run helios-mcp --verbose   # starts the MCP server over stdio
```

On first run, `helios-mcp` bootstraps `~/.helios/` (or `$HELIOS_DIR`): it
creates `base/`, `personas/`, `learned/`, `temporary/`, initializes a git
repo there, copies the default species profile and `developer`/`researcher`/
`writer` domain personas, and adds a `welcome` persona.

To wire it into an MCP client, point it at the console script, e.g. in
`.mcp.json`:

```json
{
  "mcpServers": {
    "helios": { "command": "uvx", "args": ["helios-mcp"] }
  }
}
```

### CLI

Beyond running the server, `helios-mcp` has subcommands:

```bash
uv run helios-mcp status                 # print resolved profiles for all personas
uv run helios-mcp negotiate <persona>    # show a drift report and accept/reject it
uv run helios-mcp export <persona> --format yaml|json|soulspec
uv run helios-mcp import <path> --persona NAME
uv run helios-mcp hook <event-type>      # internal: consumes Claude Code hook events on stdin
```

## Project status

The behavioral math is solid: taxonomy, distributions, hierarchy blending,
drift detection, and negotiation are implemented and covered by an extensive
test suite (see the [CI workflow](.github/workflows/ci.yml) for the current
pass/fail state — trust that badge over any number quoted in prose, since
hardcoded counts go stale). The package is at `0.4.0b1` and classified as
alpha; the protocol surface (hook coverage, import/export formats, plugin
packaging) is still being modernized. See [`PLAN.md`](PLAN.md) for the
current forward-looking plan and what's left before a stable release.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, running tests
(`uv run --frozen pytest`), linting (`uv run ruff check .`), type checking
(`uv run mypy src`), and pre-commit hooks.

## License

MIT © 2025 Anthony Kougkas — see [`LICENSE`](LICENSE).
