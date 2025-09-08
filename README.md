# ☀️ Helios MCP ☀️

**Transform stateless AI into evolving personalities with mathematical precision**

[![PyPI](https://img.shields.io/pypi/v/helios-mcp)](https://pypi.org/project/helios-mcp/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP 2025](https://img.shields.io/badge/MCP-2025--06--18-purple)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-159%20passing-brightgreen)](https://github.com/akougkas/helios-mcp)
[![Built with UV](https://img.shields.io/badge/built%20with-UV-blue?logo=python)](https://github.com/astral-sh/uv)

[![Install with uvx](https://img.shields.io/badge/install-uvx%20helios--mcp-green?style=for-the-badge&logo=python)](https://pypi.org/project/helios-mcp/)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/akougkas?logo=github)](https://github.com/sponsors/akougkas)
[![Discord](https://img.shields.io/discord/123456789?color=7289da&label=Community&logo=discord&logoColor=white)](https://discord.gg/helios-mcp)

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

## ⚡ Installation & Setup

### 🚀 Quick Install (30 seconds)

```bash
# One command to rule them all
uvx helios-mcp
```

That's it! Helios is now available as an MCP server.

### 📱 IDE Integration

<details>
<summary><b>✨ Cursor (Recommended)</b></summary>

Add to `~/.cursor/mcp.json`:
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
</details>

<details>
<summary><b>🔵 Claude Desktop</b></summary>

Add to your `claude_desktop_config.json`:
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
</details>

<details>
<summary><b>💻 VS Code / Claude Code</b></summary>

Add to your VS Code `settings.json`:
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
</details>

<details>
<summary><b>🌊 Windsurf</b></summary>

Add to your Windsurf MCP config:
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
</details>

<details>
<summary><b>🔧 Development Setup</b></summary>

For contributors and local development:
```bash
# Clone and setup
git clone https://github.com/akougkas/helios-mcp
cd helios-mcp
uv sync

# Run locally
uv run helios-mcp --verbose
```
</details>

### 🎯 First Time Setup

After installation, create your first persona:

```bash
# Helios will create ~/.helios/ automatically on first run
mkdir -p ~/.helios/personas
```

Create `~/.helios/personas/developer.yaml`:
```yaml
specialization_level: 2
behaviors:
  communication_style: "Concise with code examples"
  problem_solving: "Test-driven, iterative" 
  preferred_tools: ["pytest", "uv", "ruff"]
```

🎉 **Done!** Your AI now has persistent memory and personality.

## ✨ Features

### 🧬 Weighted Inheritance Model
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

- [Architecture](docs/ARCHITECTURE.md) - System design and implementation details
- [Development Log](DEVLOG.md) - Progress tracking and technical decisions
- [Configuration Examples](docs/samples/) - Sample base and persona configurations

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


### Learning System

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

# Run tests (159 tests passing)
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
| `uvx: command not found` | Install UV: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `No personas found` | Create `~/.helios/personas/default.yaml` |
| `Permission denied` | Check write access: `ls -la ~/.helios/` |
| `Git initialization failed` | Run `git init` in `~/.helios/` |
| `MCP connection failed` | Restart your IDE after config changes |
| `Tool not found` | Run `uvx helios-mcp` or check PATH |

**Debug Commands:**
```bash
# Verify installation
uvx helios-mcp --version

# Test with verbose logging  
uvx helios-mcp --verbose

# Check your personas
ls -la ~/.helios/personas/

# Validate YAML syntax
uv run python -c "import yaml; yaml.safe_load(open('~/.helios/base/identity.yaml'))"
```

**Still having issues?** 
- 📖 [Check our Documentation](docs/ARCHITECTURE.md)
- 🐛 [Report a bug](https://github.com/akougkas/helios-mcp/issues)
- 💬 [GitHub Discussions](https://github.com/akougkas/helios-mcp/discussions)

</details>

## 🌟 Community & Support

[![GitHub Discussions](https://img.shields.io/github/discussions/akougkas/helios-mcp)](https://github.com/akougkas/helios-mcp/discussions)
[![GitHub Issues](https://img.shields.io/github/issues/akougkas/helios-mcp)](https://github.com/akougkas/helios-mcp/issues)

- 🗣️ **Discussions**: Feature requests and Q&A  
- 🐛 **Issues**: Bug reports and fixes
- 📖 **Documentation**: [Architecture](docs/ARCHITECTURE.md) and guides
- 🎯 **Examples**: [Sample Configurations](docs/samples/)

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