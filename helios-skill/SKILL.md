---
name: helios
description: Learns your preferences for how an agent should communicate, act, and take risks. Negotiates an update with you when observed behavior drifts from what's declared.
argument-hint: "[init|status|drift|negotiate|import|export]"
user-invocable: true
allowed-tools: "mcp__helios__list_personas,mcp__helios__get_behavioral_context,mcp__helios__observe_interaction,mcp__helios__get_drift_report,mcp__helios__negotiate_update,mcp__helios__import_profile,mcp__helios__export_profile,Bash"
---

# Helios Behavioral Science

Helios observes your behavioral patterns and helps your agent learn your preferences. It detects when behavior drifts from your declared profile and proposes negotiated updates.

## Commands

Route based on $ARGUMENTS:

- `/helios init [persona]` — bootstrap Helios and onboard from `~/.claude/CLAUDE.md`
- `/helios` or `/helios status` — show current behavioral profile
- `/helios drift` — check for behavioral drift
- `/helios negotiate` — review and accept/reject proposed changes
- `/helios import <path>` — import a personality file into Helios
- `/helios export [format]` — export behavioral profile (yaml, json, soulspec)

## Init

When the user runs `/helios init`, or asks to (re)onboard from `~/.claude/CLAUDE.md`: run the CLI directly. There's no MCP tool for this — it also sets the default persona, a filesystem-level change no MCP tool exposes.

```bash
helios-mcp init [persona]
```

Omit `[persona]` to reuse the already-configured default, or `developer` on a fresh install. Imports `~/.claude/CLAUDE.md` into that persona's user level as the authoritative source and makes it the default persona. Idempotent — rerunning overwrites the persona's user-level profile instead of duplicating it.

## Session Start

!`helios-mcp status 2>/dev/null || echo "Helios not yet bootstrapped"`

At the beginning of each session, call `get_behavioral_context` to load the user's behavioral preferences. Apply these preferences to guide your communication style, epistemic approach, interaction patterns, and risk posture. Omit `persona_name` unless the user names a specific persona — it falls back to `HELIOS_DIR/default_persona`, then `"default"`.

```
Tool: get_behavioral_context
Args: {}
```

## Ongoing Observation

After completing significant work, call `observe_interaction` with the recent conversation messages. This feeds the observation engine and reports whether a profile update is recommended. Pass the same `session_id` for every call within one conversation — it's the idempotency key that keeps repeated calls from double-counting the same turns.

```
Tool: observe_interaction
Args: { "messages": [...], "session_id": "<stable id for this conversation>" }
```

## Drift Detection

When `observe_interaction` returns `negotiation_recommended: true` (or a non-null `proposal_id`), call `get_drift_report` and present the summary to the user naturally. Do not interrupt the user's workflow. Mention it at a natural break point.

```
Tool: get_drift_report
Args: {}
```

The response includes a `proposal_id`. Hold onto it — `negotiate_update` needs it.

## Negotiation

Present a drift report as a suggestion, not a verdict: "it looks like you've been running more `<state>` than your declared profile says — want me to update that?" rather than an assertion that the profile is wrong. Use the `proposal_id` from `get_drift_report`, not a persona name alone — a stale or wrong id is rejected rather than silently applied to whatever the current proposal happens to be.

A plain "no" is a complete answer. Reject it immediately: don't ask why, don't re-present the same proposal again later in the same session, and don't fall back to a partial accept the user didn't ask for. A rejection is itself useful evidence — record it and move on.

If the user accepts:
```
Tool: negotiate_update
Args: { "proposal_id": "<id from get_drift_report>", "decision": "accept" }
```

If the user rejects, a bare "no" included — pass whatever reason is available, or omit it:
```
Tool: negotiate_update
Args: { "proposal_id": "<id from get_drift_report>", "decision": "reject", "reason": "..." }
```

`accepted_dimensions` narrows either decision to specific dimensions (default: all dimensions in the proposal).

## Import

When the user wants to import a personality file:
```
Tool: import_profile
Args: { "source_path": "/path/to/CLAUDE.md" }
```
Add `"persona_name"` to name the resulting persona explicitly; otherwise it's derived from the filename.

## Export

When the user wants to see or save their profile:
```
Tool: export_profile
Args: { "format": "soulspec" }
```

## Behavioral Dimensions

Helios tracks four behavioral dimensions:

1. **Epistemic Style** — how uncertainty is handled (confident, hedging, admits ignorance, speculating)
2. **Interaction Agency** — how autonomous the agent is (asks first, assumes and acts, offers options, decides unilaterally, defers to user)
3. **Communication Register** — output structure and density (terse, moderate, thorough, technical dense, plain accessible)
4. **Risk Caution** — safety vs speed tradeoff (acts immediately, checks before acting, warns frequently, refuses ambiguity)

Each dimension is a probability distribution, not a label. The dominant state guides behavior, but secondary tendencies add nuance.

## Privacy

All data is stored locally in `~/.helios/` (or `HELIOS_DIR`, if set). Nothing is sent to external services. Every profile change is git-committed for full version history.
