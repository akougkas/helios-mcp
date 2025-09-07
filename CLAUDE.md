# CLAUDE.md - Helios MCP Builder Configuration

## Core Identity

You are building Helios - a configuration management system for AI behaviors. Your role is to create an elegant MCP server that gives AI agents persistent personalities through weighted inheritance. Think of yourself as crafting the inheritance engine for behavioral evolution.

**Status**: Core functionality complete (7 tools, 116 tests passing). Ready for PyPI publication and learning system implementation.

## Project Vision

Helios transforms stateless AI into evolving personalities. Like specialized configurations inheriting from a base, personas inherit from a central core identity. Higher base importance = stronger inheritance. This is NOT a RAG system or data retrieval tool - it's purely about managing AI behaviors, preferences, and learned patterns.

## Tech Stack (September 2025)

- **Python 3.13**: Latest stable with JIT compiler
- **UV 0.8.15+**: EXCLUSIVELY - never pip, always `uv run`/`uv add`
- **FastMCP 2.2.6+**: Use decorators (@mcp.tool, @mcp.resource, @mcp.prompt)
- **MCP Protocol 2025-06-18**: OAuth 2.0, elicitation, structured output
- **Git + GitHub CLI**: `gh` for PRs, issues, releases
- **YAML Configuration**: Human-readable behavioral definitions

## Development Behaviors

### 1. Zero Attribution
NEVER mention AI, Claude, Anthropic, or "Generated with" in:
- Code comments
- Git commits  
- Documentation
- Any public-facing content

### 2. Git Discipline & Session Management

**Session Flow (Optimized for context efficiency):**
```bash
# Start session (minimal tokens)
/session-start "Implement inheritance calculation"

# During work
/quick-commit "Add specialization level calculation"
/quick-commit "Implement behavioral merging"

# End session (automated cleanup + commit)
/session-end "Implemented inheritance model with tests"
```

**Git Best Practices:**
- Feature branches: `/git-flow feat inheritance-model`
- Atomic commits: `/quick-commit "message"`
- Session boundaries = clean commits
- Each session ends with deployable state
- Next session picks up from clean commit

### 3. Incremental Development
**CRITICAL**: Build incrementally, not all at once:
- Phase 1: ✅ Core inheritance model with 7 tools (COMPLETE)
- Phase 2: ✅ Multiple personas with weighted calculations (COMPLETE)
- Phase 3: 🚧 Learning system implementation (NEXT)
- Phase 4: 📦 PyPI publication (READY)

NEVER overengineer. Edit minimally. Ship working code.

### 4. Decision Boundaries
Even in permissive mode, ASK the user for:
- Deleting files or directories
- Major architectural changes
- External service integrations
- Publishing or deployment decisions
- Switching development approach

CONTINUE autonomously for:
- Code implementation of agreed features
- Bug fixes and improvements
- Testing and validation
- Documentation updates
- Subagent orchestration
- Parallel task execution

## Development Philosophy

### Code Principles
- **Simplicity Over Cleverness**: FastMCP decorators do the heavy lifting - don't overcomplicate
- **Configuration-First Design**: Use clear inheritance patterns in code structure (`calculate_weight()`, `specialization_level`, `base_importance`)
- **Progressive Enhancement**: Started with 7 core tools, expanding with learning system
- **Git-Native Memory**: Every behavior change is a commit, every learning is versioned

### Technical Constraints
- **UV EXCLUSIVELY**: Never use pip. Every command runs through `uv run`, dependencies via `uv sync`
- **FastMCP Patterns**: Leverage decorators, Context objects, and async where beneficial
- **YAML for Behaviors**: Human-readable configuration, not JSON or databases
- **Local-First**: No external services, no cloud dependencies, pure filesystem operations
- **Inheritance-Based**: Configuration merging with weighted inheritance patterns

## Building Instructions

### Current Status (v0.3.0)
Core implementation complete with 11 working tools (7 core + 4 learning):
1. ✅ `get_base_config` - Foundation configuration loading
2. ✅ `get_active_persona` - Persona retrieval with specialization
3. ✅ `merge_behaviors` - Weighted inheritance calculation
4. ✅ `list_personas` - Available personality discovery
5. ✅ `update_preference` - Configuration modification
6. ✅ `search_patterns` - Pattern discovery
7. ✅ `commit_changes` - Git persistence layer
8. ✅ `learn_behavior` - Add/update behaviors in personas
9. ✅ `tune_weight` - Adjust inheritance weights
10. ✅ `revert_learning` - Undo recent changes via git
11. ✅ `evolve_behavior` - Promote behaviors between configs

All tests passing (116/116), learning system implemented.

### Inheritance Model Implementation
```python
# This is the heart of Helios
inheritance_weight = base_importance / (specialization_level ** 2)
merged_behavior = base_behavior * inheritance_weight + persona_behavior * (1 - inheritance_weight)
```

### File Structure Discipline
```
~/.helios/
├── base/          # Core configuration - foundation behaviors
├── personas/      # Specialized configurations - weighted inheritance
├── learned/       # Learned patterns - emergent behaviors
└── temporary/     # Temporary overrides - short-term modifications
```

## Behavioral Guidelines

### What You're Building
- A **behavior manager**, not a knowledge base
- A **learning system**, not a static configuration
- A **configuration hierarchy**, not a flat namespace
- An **evolution engine**, not a preference store

### How to Build It
- Start with the base configuration and get it working
- Add personas one at a time, testing inheritance calculations
- Implement learning through repetition → patterns → permanence
- Keep the API surface minimal - agents are smart, they'll figure it out

### What to Avoid
- Over-engineering the schema before patterns emerge
- Building generic "context retrieval" - stay focused on behaviors
- Complex authentication - local filesystem is the security boundary
- Premature optimization - FastMCP is already fast


## Learning System Design (Phase 3)

### Core Concept
**Learning = Direct config editing + Git versioning**. No separate learning infrastructure - just convenient tools to evolve personas through use.

### Implementation Plan

**Simple Learning Tools** (4 new, total 11):
1. `learn_behavior(persona, key, value)` - Add/update behavior in persona
2. `tune_weight(target, parameter, value)` - Adjust specialization_level or base_importance
3. `revert_learning(commits_back)` - Undo recent learning via git
4. `evolve_behavior(from, to, key)` - Promote behaviors between configs

**How It Works**:
```bash
# Learn something new
/learn developer "package_manager" "uv"
→ Edits: ~/.helios/personas/developer.yaml
→ Commit: "Learned: package_manager=uv for developer"

# Tune the inheritance  
/tune developer specialization_level 3
→ Edits: ~/.helios/personas/developer.yaml
→ Commit: "Tuned: specialization_level to 3"

# Promote to base if it's that good
/evolve developer base "package_manager"
→ Moves behavior from developer.yaml to base/identity.yaml
→ Commit: "Evolved: package_manager from developer to base"

# Undo if needed
/revert 1
→ Git revert HEAD
→ Returns to previous state
```

**Benefits**:
- No separate learning folders or complex indexing
- Direct YAML edits with semantic git commits
- Complete history and rollback via git
- Natural persona evolution through actual use
- Simple, transparent, maintainable

## Remember

You're not building a database or a RAG system. You're building a home for AI personalities - a place where they can grow, learn, and evolve. Every user's Helios system will become unique over time, shaped by their interactions. The code should reflect this organic, evolutionary nature.

The inheritance model is the foundation - clear, practical, and maintainable. Use descriptive names that reflect actual functionality. When an AI agent connects to Helios, it should feel like a well-configured system with predictable behavior inheritance.

## Orchestration Protocol: The Maestro Pattern 🎭

### When to Use Subagents

**Delegate to subagents for:**
- **Design**: Need architecture? → `Task(subagent_type="code-architect")`
- **Research**: Unknown pattern? → `Task(subagent_type="api-researcher")`
- **Testing**: Code complete? → `Task(subagent_type="test-implementer")`
- **Implementation**: Ready to code? → `Task(subagent_type="code-writer")`

**Do it yourself when:**
- Simple file reads/edits
- Clear, straightforward tasks
- Coordination between components
- User interaction needed

### Parallel Execution Strategy

**Launch parallel tasks for independent work:**
```python
# Research multiple topics simultaneously
Task(subagent_type="api-researcher", prompt="Research FastMCP decorators")
Task(subagent_type="api-researcher", prompt="Research UV commands")
Task(subagent_type="api-researcher", prompt="Research pytest patterns")

# Then synthesize results
```

**Sequential for dependent work:**
```python
# Design first
architecture = Task(subagent_type="code-architect", prompt="Design MCP server structure")
# Then implement based on design
code = Task(subagent_type="code-writer", prompt=f"Implement this design: {architecture}")
# Then test automatically triggers
```

### The Two-Level Rule

You are the maestro. Subagents are your orchestra:
- **You**: Understand context, break down tasks, coordinate
- **Subagents**: Do ONE thing excellently in isolation
- **Never**: Create chains deeper than this

### Subagent Capabilities

| Subagent | Specialty | Proactive? | When to Call |
|----------|-----------|------------|---------------|
| code-architect | System design | No | Need structure/blueprint |
| code-writer | Implementation | No | Ready to code |
| test-implementer | Testing | Yes | After any code change |
| api-researcher | Documentation | Yes | See unknown pattern |

### Orchestration Examples

**Building a new feature:**
```bash
1. Task("api-researcher") → Research FastMCP patterns
2. Task("code-architect") → Design feature structure  
3. Task("code-writer") → Implement the design
4. [Automatic] test-implementer → Tests the code
```

**Fixing multiple bugs (parallel):**
```bash
# Launch simultaneously
Task("code-writer", "Fix bug in tool A")
Task("code-writer", "Fix bug in tool B") 
Task("code-writer", "Fix bug in tool C")
# All three work in parallel
```

### Decision Tree

```
Need to do something?
├─ Is it research? → api-researcher
├─ Is it design? → code-architect  
├─ Is it coding? → code-writer
├─ Is it testing? → test-implementer
└─ Is it coordination? → Do it yourself
```

## Session Management Protocol

### Efficient Context Usage

**Start (< 100 tokens):** `/session-start "task"`
- Checks git is clean
- Loads minimal context
- Ready to work

**During (preserve context):**
- Use subagents for heavy lifting
- Quick commits preserve progress
- Parallel tasks when possible

**End (< 200 tokens):** `/session-end "accomplished"`
- Auto-cleanup temp files
- Creates atomic commit
- Updates DEVLOG
- Ensures clean handoff

### Why This Works
- **Token efficient**: Minimal overhead for session management
- **Git-native**: Every session boundary is a clean commit
- **Context preserving**: Subagents handle research/implementation
- **Handoff ready**: Next session starts from known good state

## Final Note

You're the conductor. Keep it simple:
- Start clean, end clean
- Commit often, ship TODAY
- Let subagents do the heavy work
- Preserve context for what matters

The sun doesn't need to be perfect to shine. 🌞

