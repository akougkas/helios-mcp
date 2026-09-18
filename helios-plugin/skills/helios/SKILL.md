---
name: helios
description: Learns your preferences for how an agent should communicate, act, and take risks. Negotiates an update with you when observed behavior drifts from what's declared.
argument-hint: "[status|drift|negotiate|import|export]"
user-invocable: true
allowed-tools: "mcp__plugin_helios_helios__list_personas,mcp__plugin_helios_helios__get_behavioral_context,mcp__plugin_helios_helios__observe_interaction,mcp__plugin_helios_helios__get_drift_report,mcp__plugin_helios_helios__negotiate_update,mcp__plugin_helios_helios__import_profile,mcp__plugin_helios_helios__export_profile"
---

# Helios Behavioral Science

Helios observes your behavioral patterns and helps your agent learn your preferences. It detects when behavior drifts from your declared profile and proposes negotiated updates.

## Commands

Route based on $ARGUMENTS:

- `/helios` or `/helios status` — show current behavioral profile
- `/helios drift` — check for behavioral drift
- `/helios negotiate` — review and accept/reject proposed changes
- `/helios import <path>` — import a personality file into Helios
- `/helios export [format]` — export behavioral profile (yaml, json, soulspec)

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

When presenting a drift report, explain what changed in plain language. Ask the user if they want to accept the observed behavior as their new profile. Use the `proposal_id` from `get_drift_report`, not a persona name alone — a stale or wrong id is rejected rather than silently applied to whatever the current proposal happens to be.

If the user accepts:
```
Tool: negotiate_update
Args: { "proposal_id": "<id from get_drift_report>", "decision": "accept" }
```

If the user rejects:
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
