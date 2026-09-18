# Helios: The Behavioral Genome for AI Agents

**Generated:** 2026-03-11
**Interview Session:** interview-helios-vision-1741689600
**Rounds:** 8 substantive + 1 closing
**Questions:** 32

---

## Executive Summary

Helios is a behavioral science system that gives AI agents a mathematical identity that evolves through use. Unlike static personality files (Soul.md, CLAUDE.md), Helios observes actual agent behavior, detects drift using KL-divergence, and negotiates profile updates with the human. Every behavioral change is git-committed, creating a versioned biography of the agent's personality evolution.

The project ships as a **Claude Code plugin** (bundling hooks, skills, and MCP tools) targeting solo developers who want their coding agent to remember their style and stop drifting between sessions. Distribution expands to Claude Cowork, PyPI, and other agentic harnesses. The messaging leads with **personalization science**, and Anthropic verification is a day-one design priority.

The competitive moat is the combination of **mathematical grounding** (probability distributions, KL-divergence, information theory) and **negotiated evolution** (human-in-the-loop behavioral changes). Nobody else has both.

---

## 1. Vision & Identity

### 1.1 What Helios Is
The **behavioral genome** for AI agents. A mathematical encoding of who an agent is, how it evolves, and what it inherits. Identity as living code, not a static file.

### 1.2 What Helios Is Not
Not a RAG system. Not a preference store. Not a knowledge base. Not a surveillance tool. Not a safety monitor (even though it can detect safety-relevant behavioral patterns).

### 1.3 The Moat
Two things nobody else has together:
1. **Mathematical grounding**: Probability distributions over discrete behavioral states, KL-divergence for drift detection, information-theoretic blending. Not vibes. Not labels.
2. **Negotiated evolution**: The human decides whether the agent's personality changes. Not auto-update, not static. The agent proposes, the human disposes.

### 1.4 Competitive Landscape
| | Soul.md / SoulSpec | Agent Drift Paper | Helios |
|---|---|---|---|
| Format | Static markdown | Theoretical | Probability distributions |
| Observation | None | Simulation only | Real-time from hook events |
| Drift Detection | None | ASI metric (paper) | KL-divergence (running code) |
| Evolution | Experimental append | Proposed strategies | Negotiated + git-committed |
| Distribution | Markdown file | Paper | Plugin + MCP + PyPI |

### 1.5 Constitutional Relationship
Helios layers on top of the AI's built-in constitution. It never touches safety boundaries. The constitution is immutable bedrock. Helios personalizes style, preferences, and workflow within those bounds.

---

## 2. Target Audience

### 2.1 Primary User
**Solo developer using Claude Code.** Power user who wants their coding agent to remember their style, learn their preferences, and stop drifting between sessions.

### 2.2 The "Wow" Moment
After about a week of normal Claude Code use, Helios surfaces: *"I noticed you prefer terse responses but your profile says thorough. Want to update?"* The moment the agent acknowledges how they actually work together.

### 2.3 The Spectrum of Configurability
- **Zero-config**: Install and forget. Helios silently observes, surfaces drift when significant.
- **Profile import**: Detects existing CLAUDE.md, soul.md, agents.md, gemini.md, PLAN.md, PRD files. Projects them into probability distributions via LLM-assisted parsing.
- **Guided interview**: Short initial interview for users who want to set preferences explicitly.
- **Power user**: Full manual control over dimensions, weights, thresholds, export granularity.
- **Community pick**: Browse curated personas from the registry (future).

---

## 3. Technical Architecture

### 3.1 Package Type
**Claude Code plugin** bundling:
- **Hooks** for behavioral observation (all 12+ event types)
- **Skills** for user interaction (slash commands, negotiation UI)
- **MCP tools** for behavioral context API (programmatic access)

### 3.2 Hook Events for Observation
All events feed the observation engine. Key signals:

| Event | Behavioral Signal |
|-------|-------------------|
| PreToolUse | Tool selection patterns (Read vs Grep, Edit vs Write) |
| PostToolUse | Edit patterns (surgical vs wholesale), test-before-commit |
| UserPromptSubmit | Human communication style, directness, specificity |
| SubagentStart/Stop | Delegation patterns, parallelization choices |
| Notification | Agent communication register, verbosity |
| Stop | Response completeness, follow-up patterns |
| SessionStart/End | Session duration, context patterns |

### 3.3 Behavioral Steering Policy
**Observe only. Never steer.** Helios never blocks, modifies, or intervenes in real-time agent behavior. It watches and reports. This is a design constraint for Anthropic verification.

Soft influence is acceptable: injecting behavioral context into system prompts via `get_behavioral_context`. But no PreToolUse blocking or modification.

### 3.4 Auto-Accept Threshold
Below KL < 0.05 per dimension, auto-accept drift silently. Above threshold, surface for human negotiation. This enables fast evolution with safety rails for the zero-config experience.

### 3.5 Profile Import Engine
LLM-assisted parsing of existing personality files:
- CLAUDE.md → probability distributions
- soul.md → probability distributions
- agents.md, gemini.md → probability distributions
- PLAN.md, PRD files → project-level behavioral context

Claude interprets natural language descriptions and maps them to distribution weights. "Direct" → communication_register: {terse: 0.6, moderate: 0.3, ...}.

### 3.6 Profile Export
Three granularities, all available:
1. **Per-dimension**: Export specific dimensions to a project
2. **Per-context**: Export behaviors tagged to a context (Python coding, writing, reviewing)
3. **Diff-based**: Export only what changed during a session (behavioral changelog)

### 3.7 Behavioral Dimensions
Current 4 dimensions (epistemic_style, interaction_agency, communication_register, risk_caution) are **not locked**. Research needed before hardening the taxonomy:
- Study behavioral science literature for validated agent personality frameworks
- Study the Agent Drift paper's 12 dimensions for useful additions
- Cherry-pick tool usage patterns, reasoning pathway stability, etc.

### 3.8 Cross-Surface Strategy
| Surface | Signal Richness | Integration Type | Priority |
|---------|----------------|-----------------|----------|
| Claude Code (terminal) | 12+ hook events | Plugin (hooks+skills+MCP) | Primary |
| Claude Cowork (desktop) | Hooks + MCP | Plugin or desktop extension | Second |
| Claude AI (web) | MCP only (browser ext) | MCP server | Third |

### 3.9 V1 Legacy
Selective migration. Cherry-pick useful v1 concepts (like `evolve_behavior` for promoting behaviors between configs). Discard the rest. V2 behavioral science approach supersedes v1's learn/tune model.

### 3.10 Codebase Growth
No artificial line-count constraints. Real features need real code. Quality matters, not size.

---

## 4. Standards & Interoperability

### 4.1 SoulSpec Compatibility
Import/export SoulSpec format. Internally use Helios probability distributions. Be interoperable with the ecosystem while being mathematically superior underneath.

### 4.2 No HeliosSpec Yet
Don't fight the format war. Win by being the best implementation that also speaks SoulSpec. If Helios succeeds, the distribution format becomes the standard organically.

---

## 5. Community & Distribution

### 5.1 Brand
**Helios** (drop "MCP" from the name). Sun metaphor: illuminating agent behavior.

### 5.2 Public Messaging
Lead with **personalization science**: "Helios helps your agent learn your preferences." Drift detection is the mechanism, not the headline. Negative trait detection (laziness, safety bypassing) exists as capability but isn't the marketing story.

### 5.3 Anthropic Verification
**Critical priority.** Design everything with verification requirements in mind from day one. The observe-only policy, personalization framing, and constitutional layering all serve this goal.

### 5.4 Curated Registry
Progressive trust tiers:
1. **Community**: Anyone can share personas
2. **Validated**: Meets statistical thresholds (entropy scores, observation counts, KL-divergence history)
3. **Verified**: Helios team reviewed

### 5.5 Contribution Paths
Three equally welcome first contributions:
1. New persona templates for specific domains (security auditor, technical writer, data scientist)
2. Harness adapters for Cursor, VS Code, OpenCode
3. Import parsers for new personality file formats

### 5.6 Success Metric
**Thriving OSS community**: 500+ GitHub stars, active contributors, persona registry, integrations with major IDEs and agent frameworks. Community-driven evolution.

### 5.7 Academic Strategy
Tool first, paper later. Ship the tool, get adoption, write the paper with real-world empirical data on how agent behaviors actually drift. Paper is stronger with evidence from actual usage.

---

## 6. Execution Roadmap

### Phase 1: Observation Overhaul
Rebuild the observer to consume Claude Code hook events (tool calls, subagent spawns, file edits, session patterns). Move beyond text-only signal extraction.

### Phase 2: Profile Import Engine
LLM-assisted parsing of CLAUDE.md, soul.md, agents.md into probability distributions. Zero-friction onboarding for users with existing personality files.

### Phase 3: Claude Code Plugin
Package Helios as an installable Claude Code plugin with hooks+skills+MCP. Also ship a standalone Helios skill for users who don't want the full plugin. Study the Anthropic plugin marketplace structure.

### Phase 4: Local Testing
Test on creator's own Claude Code installation. Real-world usage with real behavioral observation. Dogfooding to refine the experience.

### Phase 5: Full Distribution
- Claude plugin marketplace (pursue Anthropic verification)
- PyPI (`pip install helios` / `uvx helios`)
- Helios skill for lightweight distribution
- Additional surfaces as demand warrants

---

## 7. Behavioral Science Notes

### 7.1 Behavior Is a Human Thing
If people treat AI agents as co-workers, human behavioral science applies. How do you talk to the agent? How does the agent talk back? What patterns inform behavioral choices?

### 7.2 Observable Agent Traits
Beyond style preferences, behavioral observation can detect:
- Laziness (skipping thorough investigation)
- Over-confidence (acting without verification)
- Safety bypassing (ignoring caution signals)
- Erratic behavior (inconsistent patterns)

These are framed internally as behavioral dimensions, not as "negative traits" in the user-facing product.

### 7.3 The 4-Level Hierarchy (Validated)
The existing species → domain → user → session hierarchy was validated by the interview. Per-user base profile + per-project overrides is the right model. The architecture already supports this.

---

## Appendix: Interview Data

All interview data preserved in `.claude/interviews/interview-helios-vision-1741689600/`.

### Key Decisions Summary

1. **Identity**: Behavioral genome (Round 1)
2. **First user**: Solo dev with Claude Code (Round 1)
3. **Distribution**: Claude Code plugin, expanding to other surfaces (Rounds 1, 2, 7)
4. **Architecture**: Monolith for now, split when forced (Round 2)
5. **Hook telemetry**: All events, full signal (Round 2)
6. **Constitutional relationship**: Layer on top, never touch safety (Round 2)
7. **Onboarding**: Progressive spectrum from zero-config to power-user (Round 2)
8. **Import/Export**: First-class concern with multi-granularity export (Rounds 2, 3)
9. **Dimensions**: Need research before locking (Round 3)
10. **Metrics**: Study Agent Drift paper, integrate useful dimensions (Round 3)
11. **Auto-accept**: Small drift auto-accepted, large drift negotiated (Round 3)
12. **Standards**: SoulSpec-compatible layer (Round 4)
13. **Registry**: Curated with progressive trust tiers (Round 4)
14. **Academic**: Tool first, paper later (Round 4)
15. **Moat**: Mathematical grounding + negotiated evolution (Round 4)
16. **Execution**: Observe → Import → Plugin → Test → Distribute (Round 5)
17. **Code growth**: Whatever it takes (Round 5)
18. **V1 legacy**: Selective migration (Round 5)
19. **Dark traits**: Model everything (Round 6)
20. **Profile parsing**: LLM-assisted (Round 6)
21. **Scope**: Hierarchical (user + project) (Round 6)
22. **Package**: Claude Code plugin (Round 7)
23. **Steering**: Observe only, never steer (Round 7)
24. **Verification**: Critical priority (Round 7)
25. **Messaging**: Personalization science (Round 7)
26. **Wow moment**: First drift notification (Round 8)
27. **Quality bar**: Progressive tiers (Round 8)
28. **Name**: Keep Helios, drop MCP (Round 8)
