# Helios Implementation Plan

**Created:** 2026-03-11
**Branch:** helios-v2-behavioral-science
**Starting point:** 5 MCP tools, 253 tests, ~3,900 lines, all passing
**Source of truth:** `.specs/helios-vision-2026-03-11.md` (founder interview, 28 decisions)

---

## Phase 1: Observation Overhaul

**Goal:** The observer consumes Claude Code hook events (tool calls, subagent spawns, session patterns), not just conversation text. This is the foundation for everything else.

### What exists today
`observer.py` (498 lines) extracts 4 signal types from conversation message text:
structural (length, lists, questions, hedges, code), semantic intent, decision points, user signals.
It persists observations to `~/.helios/observations/{persona}.json`.

### What needs to change

- [x] **1.1 Hook event data model**
  Create `src/helios_mcp/hook_events.py`. Define dataclasses for each hook event type Helios consumes:
  `ToolUseEvent` (tool_name, tool_input_keys, duration_ms, success, timestamp),
  `SubagentEvent` (agent_type, agent_id, event_type: start|stop, timestamp),
  `SessionEvent` (event_type: start|end, timestamp),
  `NotificationEvent` (length, timestamp),
  `UserPromptEvent` (length, question_count, timestamp).
  Include a `parse_hook_stdin(raw_json: dict) -> HookEvent` dispatcher.

- [x] **1.2 Hook signal extractors**
  Add to `observer.py` (or a new `hook_observer.py` if observer.py gets too large):
  - `extract_tool_signals(events: list[ToolUseEvent])` → tool selection patterns (Read vs Grep, Edit vs Write), tool diversity, tool ordering sequences
  - `extract_subagent_signals(events: list[SubagentEvent])` → delegation frequency, parallelization ratio, agent types chosen
  - `extract_session_signals(events: list[SessionEvent])` → session duration patterns, interaction density
  - `extract_prompt_signals(events: list[UserPromptEvent])` → directness, specificity, question frequency
  Each extractor returns weighted contributions to the 4 behavioral dimensions.

- [x] **1.3 Signal-to-distribution mapping for hook events**
  Define the mapping from hook signals to behavioral dimension weights:
  - Tool selection patterns → epistemic_style (Read-heavy = thorough), risk_caution (test-before-commit = cautious)
  - Delegation patterns → interaction_agency (high delegation = offers_options/defers_to_user)
  - Prompt patterns → communication_register (short prompts = terse user, long = thorough)
  - Response completeness → risk_caution, epistemic_style
  Document the rationale for each mapping in code comments.

- [x] **1.4 CLI hook handlers**
  Add to `cli.py`: `helios-mcp hook <event-type>` subcommands that read JSON from stdin (as Claude Code hooks provide), parse into HookEvent, and feed to observer.
  Events to handle: `pre-tool`, `post-tool`, `subagent-start`, `subagent-stop`, `session-start`, `session-end`, `notification`, `prompt-submit`, `stop`.
  Each handler is fast (< 100ms) and non-blocking. Writes to observation store, exits 0.

- [x] **1.5 Unified observation pipeline**
  Refactor `BehavioralObserver` to accept both text messages (existing) AND hook events (new).
  Single `observe()` method dispatches to the right extractor based on input type.
  Accumulated distributions merge text-derived and hook-derived signals with configurable weights.

- [x] **1.6 Auto-accept small drift**
  Add to `drift.py`: if total KL-divergence < 0.05 per dimension, auto-apply the observed distribution as the new declared profile. Silent. No negotiation. Git commit with message: `"Auto-evolved: minor drift in {dimension}"`.
  Add `auto_accept_threshold` to `HeliosConfig` (default: 0.05).

- [x] **1.7 Tests for hook observation**
  `tests/test_hook_events.py` — event parsing, validation, edge cases.
  `tests/test_hook_observer.py` — signal extraction from tool/subagent/session/prompt events.
  `tests/test_auto_accept.py` — auto-accept below threshold, negotiate above.
  `tests/test_unified_observer.py` — mixed text + hook signal pipeline.
  Target: all existing 253 tests still pass + new tests.

- [x] **1.8 Run full test suite, fix any regressions**
  `uv run pytest tests/ -q` — every test passes. No regressions from the overhaul.

---

## Phase 2: Profile Import/Export Engine

**Goal:** Users can import existing CLAUDE.md / soul.md / agents.md files into Helios probability distributions, and export behavioral profiles in multiple granularities.

### Import

- [ ] **2.1 Import module**
  Create `src/helios_mcp/importer.py`.
  `import_from_markdown(path: Path, format: str = "auto") -> BehavioralProfile`
  Format detection: auto-detect CLAUDE.md vs soul.md vs agents.md vs gemini.md by content patterns.
  Parsing strategy: extract personality-relevant text blocks (tone directives, behavioral rules, style instructions) from the markdown.
  Return a structured representation ready for LLM-assisted projection.

- [ ] **2.2 LLM-assisted projection**
  Create `src/helios_mcp/projector.py`.
  `project_to_distributions(text_blocks: list[str], taxonomy: dict) -> dict[str, BehavioralDistribution]`
  Constructs a prompt that asks Claude to map natural language personality descriptions to probability distributions over the 4 behavioral dimensions.
  The prompt includes the taxonomy states with descriptions and asks for float weights that sum to 1.0.
  Returns validated `BehavioralDistribution` objects.
  Fallback: if no LLM available, use keyword-based heuristic mapping (deterministic, lower quality).

- [ ] **2.3 MCP tool: import_profile**
  Add to `server.py`: `import_profile(source_path: str, persona_name: str) -> dict`
  Reads the file, projects to distributions, saves as a new persona YAML, git-commits.
  Returns the created profile summary.

- [ ] **2.4 CLI: helios-mcp import**
  `helios-mcp import <path> [--persona NAME] [--format auto|claude|soul|agents]`
  Interactive confirmation before saving. Shows the projected distributions before committing.

### Export

- [ ] **2.5 Export module**
  Create `src/helios_mcp/exporter.py`.
  Three export modes:
  - `export_dimensions(profile, dimensions: list[str]) -> dict` — per-dimension slice
  - `export_context(profile, context_tag: str) -> dict` — future: context-tagged behaviors
  - `export_diff(profile, commits_back: int = 1) -> dict` — behavioral changelog from git history
  All return serializable dicts suitable for YAML/JSON output.

- [ ] **2.6 SoulSpec-compatible export**
  `export_soulspec(profile) -> str` — renders a BehavioralProfile as a SoulSpec-compatible SOUL.md file.
  Maps probability distributions back to natural language personality descriptions.
  Includes metadata comments showing the underlying distribution values.

- [ ] **2.7 MCP tool: export_profile**
  Add to `server.py`: `export_profile(persona_name: str, format: str = "yaml", dimensions: list[str] | None = None) -> dict`

- [ ] **2.8 CLI: helios-mcp export**
  `helios-mcp export <persona> [--format yaml|json|soulspec] [--dimensions dim1,dim2] [--diff N]`

- [ ] **2.9 Tests for import/export**
  `tests/test_importer.py` — format detection, markdown parsing, edge cases.
  `tests/test_projector.py` — projection prompt construction, distribution validation, keyword fallback.
  `tests/test_exporter.py` — all three export modes, SoulSpec format, round-trip (import→export→import produces same distributions).
  Target: no regressions + new tests passing.

---

## Phase 3: Claude Code Plugin Packaging

**Goal:** Helios ships as an installable Claude Code plugin that bundles hooks, skills, and MCP. Also ship a standalone skill for lightweight adoption.

### Plugin structure

- [ ] **3.1 Create plugin directory layout**
  ```
  helios-plugin/
  ├── .claude-plugin/
  │   └── plugin.json
  ├── hooks/
  │   └── hooks.json
  ├── skills/
  │   └── helios/
  │       └── SKILL.md
  ├── agents/
  │   └── helios-observer.md
  ├── .mcp.json
  └── README.md
  ```

- [ ] **3.2 plugin.json manifest**
  Name: "helios", description, version, author, keywords (behavioral, personality, drift, personalization).
  Component declarations pointing to hooks/, skills/, agents/, .mcp.json.

- [ ] **3.3 hooks.json — behavioral observation hooks**
  Define hooks for all observed events. Each hook runs `helios-mcp hook <event-type>` as a command hook.
  ```json
  {
    "hooks": {
      "PostToolUse": [{"matcher": {}, "hooks": [{"type": "command", "command": "helios-mcp hook post-tool"}]}],
      "SubagentStop": [{"matcher": {}, "hooks": [{"type": "command", "command": "helios-mcp hook subagent-stop"}]}],
      "Stop": [{"matcher": {}, "hooks": [{"type": "command", "command": "helios-mcp hook stop"}]}],
      "SessionStart": [{"matcher": {}, "hooks": [{"type": "command", "command": "helios-mcp hook session-start"}]}],
      "SessionEnd": [{"matcher": {}, "hooks": [{"type": "command", "command": "helios-mcp hook session-end"}]}]
    }
  }
  ```
  Observe-only. No PreToolUse blocking. No modification of tool inputs.

- [ ] **3.4 .mcp.json — MCP server config**
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

- [ ] **3.5 Helios skill (SKILL.md)**
  Create `skills/helios/SKILL.md` with:
  - Skill activation triggers: `/helios`, `/helios status`, `/helios drift`, `/helios negotiate`, `/helios import`, `/helios export`
  - Instructions for Claude on how to use the MCP tools
  - Behavioral context injection guidance (call `get_behavioral_context` at session start)
  - Drift check guidance (call `get_drift_report` periodically or on session end)
  - Negotiation flow (when drift is detected, present proposal to user naturally)

- [ ] **3.6 Observer agent (helios-observer.md)**
  Agent definition for background behavioral analysis. Can be spawned by the skill to analyze accumulated observations and generate insights beyond simple drift reports.

- [ ] **3.7 Standalone skill package**
  For users who want Helios without the full plugin (no hooks, just MCP + skill):
  Create a separate `helios-skill/` directory with just `SKILL.md` and `.mcp.json`.
  Users install via: `claude plugin add helios-skill` or copy SKILL.md into `.claude/skills/`.

- [ ] **3.8 Plugin installation test**
  Verify the plugin installs correctly:
  `claude plugin add ./helios-plugin/`
  Verify hooks register, MCP server starts, skill activates.
  Document any issues.

---

## Phase 4: Local Dogfooding

**Goal:** Install on creator's Claude Code. Real-world usage for at least 5 sessions. Identify bugs, UX friction, and missing features.

- [ ] **4.1 Install Helios plugin locally**
  Install on creator's machine. Verify all components: hooks firing, MCP tools available, skill responding to `/helios`.

- [ ] **4.2 Bootstrap first profile**
  Run initial profile creation. Import creator's existing CLAUDE.md (the global one at `~/.claude/CLAUDE.md`) into Helios distributions. Verify the projected profile feels accurate.

- [ ] **4.3 5-session observation run**
  Use Claude Code normally for 5 full sessions. Let hooks collect behavioral data. Check:
  - Are observations accumulating correctly?
  - Is the observation store growing reasonably (not bloating)?
  - Are hook handlers fast enough (< 100ms)?
  - Is the MCP server stable across sessions?

- [ ] **4.4 First drift report**
  After sufficient observations (20+), request drift report. Evaluate:
  - Does the drift summary make sense?
  - Are the per-dimension readings plausible?
  - Is the negotiation proposal reasonable?

- [ ] **4.5 First negotiation**
  Accept or reject a profile update. Verify git commit happens. Check the updated YAML is valid and the profile feels right.

- [ ] **4.6 Bug fix pass**
  Fix all issues discovered during dogfooding. Update tests. Ensure 100% test pass rate.

- [ ] **4.7 UX refinement pass**
  Based on dogfooding experience:
  - Adjust signal weights if distributions feel off
  - Tune drift thresholds if notifications are too frequent or too rare
  - Improve drift report natural language quality
  - Simplify any friction in the negotiation flow

---

## Phase 5: Distribution

**Goal:** Helios available on all target surfaces. Anthropic verification submitted.

### PyPI

- [ ] **5.1 Package metadata cleanup**
  Update `pyproject.toml`: name "helios" (or "helios-behavioral" if "helios" is taken), description, keywords, classifiers, project URLs, README rendering.

- [ ] **5.2 Version bump to v1.0.0**
  This is the first public release with the full behavioral science stack. Bump from 0.3.0 to 1.0.0.

- [ ] **5.3 PyPI publish**
  `uv build --wheel && uv publish` (or twine). Verify `uvx helios-mcp` works from a clean environment. Verify `pip install helios-mcp` works.

### Claude Plugin Marketplace

- [ ] **5.4 Prepare marketplace submission**
  Follow Anthropic's submission guidelines. Ensure plugin.json is complete. README covers installation, usage, privacy (what data Helios collects, where it's stored, that it's local-only).

- [ ] **5.5 Submit to Anthropic marketplace**
  Submit PR to `anthropics/claude-plugins-official` or use the submission process at claude.com/plugins. Target: Anthropic Verified badge.

### Documentation

- [ ] **5.6 README overhaul**
  Rewrite README.md for the Helios (not Helios MCP) brand. Lead with personalization science framing. Include:
  - One-line pitch
  - 30-second install (plugin or uvx)
  - Screenshot/GIF of drift notification
  - How it works (observe → drift → negotiate → evolve)
  - Privacy statement (local-only, git-versioned, no cloud)

- [ ] **5.7 User guide**
  `docs/user-guide.md`: full walkthrough from install to first drift report to exporting profiles.

- [ ] **5.8 Contributor guide**
  `CONTRIBUTING.md`: how to add persona templates, harness adapters, import parsers. The three contribution paths from the interview.

### Stretch

- [ ] **5.9 GitHub release**
  Create GitHub release v1.0.0 with changelog, binary attachments if applicable.

- [ ] **5.10 Community announcement**
  Draft announcement for relevant channels (Claude Code community, Twitter/X, Reddit r/ClaudeAI, Hacker News). Personalization science framing. Link to plugin and PyPI.

---

## Execution Protocol

Each session should:
1. Read `PLAN.md` to find the first unchecked `[ ]` task
2. Implement it fully (no stubs, no TODOs)
3. Write tests
4. Run `uv run pytest tests/ -q` and fix failures
5. Mark task `[x]` in this file
6. Commit with format: `helios: [Phase.Task] description`
7. Move to next task

**Rules:**
- Never skip a task to do a later one (dependencies are ordered)
- Never commit broken tests
- If a task is too large for one session, split it and note partial progress
- After each commit, update the "Last completed" line below

**Last completed:** 1.8 Full test suite verification (Phase 1 complete)
**Current phase:** Phase 2 — Profile Import/Export Engine
**Tests passing:** 403 (253 baseline + 150 new)
