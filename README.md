# ☀️ Helios MCP

**Transform stateless AI into evolving personalities with mathematical precision**

[![PyPI](https://img.shields.io/pypi/v/helios-mcp)](https://pypi.org/project/helios-mcp/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP 2025](https://img.shields.io/badge/MCP-2025--06--18-purple)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-116%20passing-brightgreen)](https://github.com/akougkas/helios-mcp)

## 🚀 What is Helios?

Helios is a configuration persistence engine that gives AI agents long-term memory and evolving personalities through weighted behavioral inheritance. Unlike RAG systems that retrieve knowledge, Helios manages **how** your AI behaves, not **what** it knows.

### The Problem It Solves

Every AI conversation today starts from zero. You explain your preferences, working style, and context repeatedly. Your AI assistant has no memory of who you are or how you like to work. **Helios changes that.**

### The Solution

Helios provides a mathematical framework for AI personality evolution:
- **Base configurations** define core behaviors (70% influence)
- **Specialized personas** adapt to specific contexts (30% influence)
- **Learning system** captures patterns from actual usage
- **Git versioning** tracks every behavioral change

This isn't prompt engineering - it's personality engineering.

## ⚡ Quick Start

### Installation (30 seconds)

```bash
# Via UV (recommended - already installed on most systems)
uvx helios-mcp

# For development/testing
git clone https://github.com/akougkas/helios-mcp
cd helios-mcp
uv sync
uv run helios-mcp
```

### Configuration (2 minutes)

**Claude Desktop**
```json
{
  "mcpServers": {
    "helios": {
      "command": "uvx",
      "args": ["helios-mcp", "--helios-dir", "~/.helios"]
    }
  }
}
```

**VS Code / Cursor**
```json
{
  "mcp.servers": {
    "helios": {
      "command": "uvx",
      "args": ["helios-mcp"]
    }
  }
}
```

### Your First Persona (1 minute)

```yaml
# ~/.helios/personas/developer.yaml
specialization_level: 2
behaviors:
  communication_style: "Concise with code examples"
  problem_solving: "Test-driven, iterative"
  preferred_tools: ["pytest", "uv", "ruff"]
```

That's it! Your AI now has a persistent developer personality.

## ✨ Features

### 🧬 Mathematical Inheritance Model
```python
# The core formula that powers Helios
inheritance_weight = base_importance / (specialization_level ** 2)
final_behavior = base * inheritance_weight + persona * (1 - inheritance_weight)
```

### 🎯 Multi-Persona Support
- **Developer**: Technical, test-driven, loves clean code
- **Researcher**: Academic, citation-focused, methodical
- **Creative**: Imaginative, narrative-driven, experimental
- **Custom**: Define any personality you need

### 📊 Git-Powered Memory
- Every configuration change is versioned
- Roll back to any previous personality state
- Track behavioral evolution over time
- Collaborative persona development

### 🔧 MCP Native
Built specifically for the Model Context Protocol with 11 powerful tools for AI agents to manage their own evolution (7 core + 4 learning).

## 📚 Documentation

- [Architecture](ARCHITECTURE.md) - System design and implementation details
- [Development Log](DEVLOG.md) - Progress tracking and technical decisions
- [Contributing](CONTRIBUTING.md) - How to contribute to Helios

---

## 🤖 AI Agent Integration Guide

*This section provides detailed technical information for AI agents using Helios MCP.*

### Available MCP Tools

Helios exposes 11 tools through the Model Context Protocol (7 core + 4 learning):

| Tool | Parameters | Returns | Purpose |
|------|------------|---------|----------|
| `get_base_config` | None | `{base_importance: float, behaviors: dict}` | Load foundation configuration |
| `get_active_persona` | `name: str` | `{specialization_level: int, behaviors: dict}` | Retrieve persona configuration |
| `merge_behaviors` | `base: dict, persona: dict` | `{merged: dict, weights: dict}` | Calculate inheritance |
| `list_personas` | None | `[{name: str, level: int}]` | List available personas |
| `update_preference` | `path: str, value: any` | `{success: bool}` | Modify configuration |
| `search_patterns` | `confidence: float` | `[{pattern: str, score: float}]` | Find learned behaviors |
| `commit_changes` | `message: str` | `{commit_id: str}` | Version changes |
| **Learning Tools** | | | |
| `learn_behavior` | `persona: str, key: str, value: any` | `{old_value, new_value}` | Add/update behaviors |
| `tune_weight` | `target: str, parameter: str, value: float` | `{old_value, new_value}` | Adjust weights |
| `revert_learning` | `commits_back: int` | `{reverted_commits}` | Undo via git |
| `evolve_behavior` | `from: str, to: str, key: str` | `{direction, value}` | Migrate behaviors |

### Inheritance Calculation Algorithm

```python
def calculate_inheritance(base_importance: float, specialization_level: int) -> float:
    """
    Calculate how much influence the base configuration has.
    
    Higher specialization_level = less base influence
    Higher base_importance = more base influence
    
    Returns: weight between 0.01 and 1.0
    """
    weight = base_importance / (specialization_level ** 2)
    return max(0.01, min(1.0, weight))
```

### Configuration Schema

**Base Configuration** (`~/.helios/base/identity.yaml`):
```yaml
base_importance: 0.7  # float: 0.0-1.0, influence strength
behaviors:
  communication_style: str
  problem_solving: str
  preferred_frameworks: [str]
metadata:
  version: str
  created: datetime
```

**Persona Configuration** (`~/.helios/personas/{name}.yaml`):
```yaml
specialization_level: 2  # int: >= 1, higher = more specialized
behaviors:
  # Overrides or extends base behaviors
  communication_style: str
  domain_expertise: str
metadata:
  inherits_from: "base"
  version: str
```

### Behavioral Merging Rules

1. **Scalar values** (strings, numbers): Weighted selection based on inheritance
2. **Lists**: Concatenation with deduplication, weighted ordering
3. **Nested dictionaries**: Recursive merging with same rules
4. **Missing keys**: Inherited from base if not in persona

### Example Integration

```python
# AI agent using Helios to load personality
async def load_personality(mcp_client, context):
    # Get base configuration
    base = await mcp_client.call_tool("get_base_config")
    
    # Determine appropriate persona from context
    persona_name = detect_context(context)  # e.g., "developer", "researcher"
    
    # Load and merge
    persona = await mcp_client.call_tool("get_active_persona", {"name": persona_name})
    merged = await mcp_client.call_tool("merge_behaviors", {
        "base": base,
        "persona": persona
    })
    
    # Apply behavioral configuration
    return merged["merged"]
```

### Learning System (v0.3.0)

Learning tools that directly edit configurations:
- `learn_behavior(persona, key, value)` - Add/update behaviors
- `tune_weight(target, parameter, value)` - Adjust inheritance weights
- `revert_learning(commits_back)` - Undo recent learning via git
- `evolve_behavior(from, to, key)` - Promote behaviors between configs

All learning is tracked through git, providing complete history and rollback capability.

---

## 💡 Use Cases

### Real-World Scenarios

**Software Development Team**
- Morning: Load "architect" persona for system design
- Afternoon: Switch to "debugger" for troubleshooting
- Code review: Use "mentor" persona for teaching

**Research & Writing**
- Literature review: "researcher" persona
- Data analysis: "statistician" persona
- Paper writing: "academic_writer" persona

**Personal Assistant**
- Work hours: Professional, formal communication
- Personal time: Casual, friendly interaction
- Learning mode: Patient, educational approach

## 🛠️ Development

```bash
# Clone and setup
git clone https://github.com/akougkas/helios-mcp
cd helios-mcp
uv sync

# Run tests (currently 116 passing)
uv run pytest

# Run with local changes
uv run helios-mcp --verbose
```

### Tech Stack
- **Python 3.13** with JIT compiler
- **FastMCP 2.2.6+** for MCP protocol
- **UV** for dependency management
- **Git** for versioning
- **YAML** for configurations

## 🐛 Troubleshooting

<details>
<summary>Common Issues & Solutions</summary>

| Issue | Solution |
|-------|----------|
| "Tool not found" | Run `uvx helios-mcp` or check PATH |
| "No personas" | Create a `.yaml` file in `~/.helios/personas/` |
| "Permission denied" | Check write permissions for `~/.helios/` |
| "Git error" | Helios auto-initializes git, check `.helios/.git/` |

**Debug Commands:**
```bash
# Check installation
uvx helios-mcp --version

# Verbose logging
uvx helios-mcp --verbose

# Verify config directory
ls -la ~/.helios/
```
</details>

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution
```bash
# Fork, clone, branch
git checkout -b feature/your-feature

# Make changes, test
uv run pytest

# Submit PR
gh pr create
```

## 📄 License

MIT © 2025 Anthony Kougkas

## 🙏 Acknowledgments

Built for the [Model Context Protocol](https://modelcontextprotocol.io/) ecosystem. Special thanks to the MCP community and early adopters.

---

<div align="center">

**Transform your AI from stateless to sophisticated**

```bash
uvx helios-mcp
```

Built with ☀️ by humans, for AI

[Report Bug](https://github.com/akougkas/helios-mcp/issues) · [Request Feature](https://github.com/akougkas/helios-mcp/issues) · [Documentation](https://github.com/akougkas/helios-mcp/wiki)

</div>