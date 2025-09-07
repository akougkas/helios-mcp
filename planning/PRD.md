# Helios MCP: The AI Behavior Solar System

## Vision

Helios transforms AI agents from stateless tools into evolving personalities with persistent memory, learned behaviors, and user-specific adaptations. Like a solar system where planets orbit a central star, AI behaviors orbit around a core identity, with each specialized persona maintaining its own trajectory while remaining gravitationally bound to fundamental principles.

## Problem Statement

Current AI agents reset with every session, forgetting user preferences, learned patterns, and accumulated wisdom. Users must repeatedly teach the same preferences, explain their context, and rebuild their working relationship. Meanwhile, agents cannot learn from experience or evolve their behaviors based on what works.

Helios solves this by creating a persistent, git-versioned behavioral management system where:
- Users define their core identity once, and it persists forever
- Agents learn from interactions and evolve their behaviors
- Specialized personas (coding, research, creative) inherit from a central core
- All learning is version-controlled and portable across machines

## The Solar System Model

### Core Concepts

**Helios Core (The Sun)**: The gravitational center containing fundamental identity, values, and base behaviors that all personas inherit.

**Personas (Planets)**: Specialized behavioral configurations that orbit the core. Closer orbits mean stronger inheritance from core behaviors; distant orbits allow more specialization.

**Behavioral Gravity**: Inheritance strength determined by orbital distance. A coding persona (close orbit) strongly inherits core communication style, while a creative persona (distant orbit) can diverge more.

**Alignments**: When multiple personas work together on complex tasks, they align like planetary conjunctions, combining their capabilities.

**Orbital Resonance**: Patterns that repeat successfully achieve "stability" and become permanent parts of the behavioral system.

## Key Objectives

1. **Persistent Personality**: Give AI agents consistent identity across sessions
2. **Behavioral Evolution**: Allow agents to learn and improve from experience  
3. **User Sovereignty**: Users control their AI's personality through version-controlled instructions
4. **Multi-Agent Coordination**: Different AI providers (Claude, GPT, Gemini) share learned behaviors
5. **Zero-Friction Deployment**: Works locally on any machine with Python and git

## Value Propositions

### For Users
- **Personalization at Scale**: Your AI knows you, your preferences, and your patterns
- **Compound Learning**: Every interaction makes future interactions better
- **Portable Identity**: Your AI personality travels with you across machines via git
- **Behavioral Control**: Full visibility and control over what your AI learns

### For AI Agents  
- **Contextual Intelligence**: Access to accumulated wisdom and patterns
- **Self-Improvement**: Ability to propose and commit behavioral refinements
- **Specialized Capabilities**: Load appropriate personas for specific tasks
- **Cross-Session Continuity**: Remember important context and decisions

## Technical Architecture

### MCP Server Built with FastMCP 2.2.6+ - UV EXCLUSIVE (September 2025)
Helios is implemented as a Python MCP server using FastMCP 2.2.6+, adhering to the MCP Protocol 2025-06-18 specification, managed EXCLUSIVELY with UV 0.8.15+:

- **FastMCP 2.2.6+**: High-level Pythonic framework with decorators (@mcp.tool, @mcp.resource, @mcp.prompt)
- **MCP Protocol 2025-06-18**: Latest specification with OAuth 2.0 auth, elicitation support, and structured tool output
- **UV 0.8.15+**: Extremely fast Rust-based Python package manager (10-100x faster than pip)
- **Python 3.13**: Latest stable release with JIT compiler and free-threaded mode support
- **Type Safety**: Full Pydantic v2 models and Python 3.13 type hints
- **Async-First**: All tools and resources use async/await patterns
- **Context Injection**: FastMCP Context for logging, progress reporting, and sampling

### Development Requirements
- UV >= 0.8.15 (Astral's Python package manager - September 2025)
- Python 3.13 managed by UV (`uv python install 3.13`)
- Git for version control
- FastMCP >= 2.2.6 with full MCP 2025-06-18 spec support

### File-Based Backend
All behaviors stored as YAML/Markdown files in a git repository:
```
~/.helios/
├── core/           # Solar core - fundamental identity
├── personas/       # Planets - specialized behaviors  
├── experiences/    # Learned patterns and adaptations
├── transients/     # Temporary behavioral modifications
├── config/         # System configuration
├── resources/      # MCP resource templates
├── prompts/        # Reusable prompt templates
└── .git/           # Version control for all changes
```

### Integration Points
- **Obsidian**: Native integration via MCP resources for vault-based memory systems
- **Git**: GitPython 3.1.43+ for version control and multi-machine sync
- **MCP Clients**: Compatible with Claude Desktop, OpenAI Agents SDK, Gemini (2025 adoption)
- **FastMCP Features**: Server composition, OpenAPI generation, authentication, middleware
- **Local Filesystem**: Simple, reliable, privacy-preserving with Path and asyncio
- **Python Ecosystem**: Rich 3.13 ecosystem with Pydantic, Typer, HTTPx, Rich

## Success Metrics

1. **Behavioral Consistency**: Same preferences applied across 100% of sessions
2. **Learning Velocity**: New patterns recognized and suggested within 3 occurrences
3. **Setup Time**: Under 5 minutes from install to personalized agent
4. **Cross-Machine Sync**: Changes propagate to all machines within one git pull
5. **Agent Agnostic**: Works with any MCP-compatible AI system

## Non-Goals

- Helios is NOT a RAG system for project data
- Helios is NOT a general-purpose context retrieval engine
- Helios is NOT a cloud service - it runs entirely locally
- Helios does NOT handle synchronization - delegates to git/Obsidian
