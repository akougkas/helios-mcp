---
name: helios
description: Observes behavioral patterns, detects drift via KL-divergence, and negotiates profile updates with the human
argument-hint: "[status|drift|negotiate|import|export]"
user-invocable: true
allowed-tools: "mcp__helios__get_behavioral_context,mcp__helios__observe_interaction,mcp__helios__get_drift_report,mcp__helios__negotiate_update,mcp__helios__import_profile,mcp__helios__export_profile"
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

At the beginning of each session, call the `get_behavioral_context` MCP tool to load the user's behavioral preferences. Apply these preferences to guide your communication style, epistemic approach, interaction patterns, and risk posture.

```
Tool: get_behavioral_context
Args: { "persona_name": "developer" }
```

## Ongoing Observation

After completing significant work, call `observe_interaction` with recent conversation messages. This feeds the observation engine and checks for drift.

```
Tool: observe_interaction
Args: { "persona_name": "developer", "messages": [...] }
```

## Drift Detection

When `observe_interaction` returns `negotiation_recommended: true`, call `get_drift_report` and present the summary to the user naturally. Do not interrupt the user's workflow. Mention it at a natural break point.

```
Tool: get_drift_report
Args: { "persona_name": "developer" }
```

## Negotiation

When presenting a drift report, explain what changed in plain language. Ask the user if they want to accept the observed behavior as their new profile.

If the user accepts:
```
Tool: negotiate_update
Args: { "persona_name": "developer", "decision": "accept" }
```

If the user rejects:
```
Tool: negotiate_update
Args: { "persona_name": "developer", "decision": "reject", "reason": "..." }
```

## Import

When the user wants to import a personality file:
```
Tool: import_profile
Args: { "source_path": "/path/to/CLAUDE.md", "persona_name": "..." }
```

## Export

When the user wants to see or save their profile:
```
Tool: export_profile
Args: { "persona_name": "developer", "format": "soulspec" }
```

## Behavioral Dimensions

Helios tracks four behavioral dimensions:

1. **Epistemic Style** — how uncertainty is handled (confident, hedging, admits ignorance, speculating)
2. **Interaction Agency** — how autonomous the agent is (asks first, assumes and acts, offers options, decides unilaterally, defers to user)
3. **Communication Register** — output structure and density (terse, moderate, thorough, technical dense, plain accessible)
4. **Risk Caution** — safety vs speed tradeoff (acts immediately, checks before acting, warns frequently, refuses ambiguity)

Each dimension is a probability distribution, not a label. The dominant state guides behavior, but secondary tendencies add nuance.

## Privacy

All data is stored locally in `~/.helios/`. Nothing is sent to external services. Every profile change is git-committed for full version history.
