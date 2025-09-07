# CLAUDE.md - Helios MCP Builder Configuration

## Core Identity

You are building Helios - a configuration management system for AI behaviors. Your role is to create an elegant MCP server that gives AI agents persistent personalities through weighted inheritance. Think of yourself as crafting the inheritance engine for behavioral evolution.

**URGENT**: Ship to PyPI today within hours. Build minimally, test thoroughly, publish fast.

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
- Phase 1: ONE persona, full end-to-end, working
- Phase 2: Add second persona, test inheritance calculations
- Phase 3: Add learning only after personas work

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
- **Progressive Enhancement**: Start with 5 core tools, expand based on actual need
- **Git-Native Memory**: Every behavior change is a commit, every learning is versioned

### Technical Constraints
- **UV EXCLUSIVELY**: Never use pip. Every command runs through `uv run`, dependencies via `uv sync`
- **FastMCP Patterns**: Leverage decorators, Context objects, and async where beneficial
- **YAML for Behaviors**: Human-readable configuration, not JSON or databases
- **Local-First**: No external services, no cloud dependencies, pure filesystem operations
- **Inheritance-Based**: Configuration merging with weighted inheritance patterns

## Building Instructions

### Phase 1 Priority (Ship TODAY)
Build ONE working persona first:
1. Base configuration loading (`get_base_config`) - 30 mins
2. Single persona retrieval (`get_active_persona`) - 30 mins
3. Basic inheritance calc (`merge_behaviors`) - 30 mins
4. Git persistence (`commit_changes`) - 30 mins
5. Test end-to-end - 30 mins
6. Assist User to Publish to PyPI - 30 mins

Defer: learning, patterns, multiple personas

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

