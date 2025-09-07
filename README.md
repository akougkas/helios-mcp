# ☀️ Helios MCP

**Give your AI persistent personality through mathematical inheritance**

[![PyPI](https://img.shields.io/pypi/v/helios-mcp)](https://pypi.org/project/helios-mcp/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP 2025](https://img.shields.io/badge/MCP-2025--06--18-purple)](https://modelcontextprotocol.io/)

## The Problem

### ❌ Without Helios
- 🔄 **Stateless AI** - Every conversation starts from zero
- 📝 **Manual prompts** - Repeat preferences in every session  
- 🎭 **No specialization** - Same personality for coding and writing
- 💾 **No memory** - Learned patterns disappear

### ✅ With Helios
- 🧬 **Evolving personality** - AI remembers and adapts
- ⚖️ **Mathematical inheritance** - Precise control over specialization
- 🎯 **Domain personas** - Different personalities for different tasks
- 📊 **Git-versioned evolution** - Track behavioral changes over time

## The Magic: Weighted Behavioral Inheritance

```python
# Not configuration merging. Mathematical personality inheritance.
inheritance_weight = base_importance / (specialization_level ** 2)
merged_behavior = base * inheritance_weight + persona * (1 - inheritance_weight)
```

**Real example:**
```yaml
base_importance: 0.7      # Strong foundation
specialization_level: 2    # Moderate specialization
→ inheritance: 17.5% base, 82.5% persona
```

## Installation

### Via UV (Recommended)
```bash
uvx helios-mcp
```

### Claude Desktop
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

### VS Code / Cursor
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

## Quick Start

```bash
# Install and run
uvx helios-mcp

# Custom configuration directory
uvx helios-mcp --helios-dir ~/my-ai-config

# With verbose logging
uvx helios-mcp --verbose
```

## How It Works

### Inheritance in Action

```yaml
# ~/.helios/base/identity.yaml
base_importance: 0.7
behaviors:
  communication_style: "Direct and technical"
  problem_solving: "First principles thinking"
  
# ~/.helios/personas/coder.yaml  
specialization_level: 2
behaviors:
  communication_style: "Detailed with code examples"
  problem_solving: "Implementation-focused"
  preferred_languages: ["Python", "TypeScript"]
```

**Result:** `17.5% base + 82.5% coder = Your specialized coding assistant`

### The Inheritance Flow

```
Base Identity (70% importance)
    ↓
Specialization Level² (2² = 4)
    ↓
Inheritance Weight (70% / 4 = 17.5%)
    ↓
Merged Behavior (17.5% base + 82.5% persona)
    ↓
Git Commit (versioned evolution)
```

## Available Tools

Helios provides 7 MCP tools for managing AI behaviors:

| Tool | Description |
|------|-------------|
| `get_base_config` | Load foundation behaviors and inheritance settings |
| `get_active_persona` | Retrieve specialized persona configuration |
| `merge_behaviors` | Calculate weighted inheritance between base and persona |
| `list_personas` | Show all available personality configurations |
| `update_preference` | Modify and persist behavioral preferences |
| `search_patterns` | Find learned patterns by confidence level |
| `commit_changes` | Version control behavioral evolution with Git |

## Use Cases

### Multi-Domain Assistant
```yaml
personas/
├── researcher.yaml     # Academic writing, citations
├── developer.yaml      # Code generation, debugging
└── creative.yaml       # Storytelling, brainstorming
```

### Learning System
```yaml
learned/
├── successful_patterns.yaml    # What worked
├── user_preferences.yaml       # Discovered preferences
└── domain_expertise.yaml       # Accumulated knowledge
```

## Architecture

Helios is NOT a RAG system or knowledge base. It's a behavioral inheritance engine:

- **Configuration Management** - YAML-based behavioral definitions
- **Inheritance Calculator** - Mathematical weighting system
- **Git Persistence** - Every change is versioned
- **MCP Integration** - Works with any MCP-compatible AI client

### File Structure
```
~/.helios/
├── base/           # Core identity configuration
├── personas/       # Specialized personalities
├── learned/        # Patterns discovered over time
└── .git/           # Behavioral evolution history
```

## Advanced Configuration

### Custom Inheritance Models

```python
# Stronger base influence for conservative evolution
base_importance: 0.9
specialization_level: 1

# Highly specialized with minimal base
base_importance: 0.3
specialization_level: 5
```

### Lifecycle Management

Helios includes production-ready lifecycle management:

- **Health monitoring** - Automatic recovery from failures
- **Graceful shutdown** - Complete operations before exit
- **Resource cleanup** - Prevent memory leaks
- **Operation tracking** - Ensure git commits complete

```bash
# With health monitoring (default: 60s)
uvx helios-mcp --health-check-interval 60

# Custom shutdown timeout
uvx helios-mcp --shutdown-timeout 30
```

## Development

```bash
# Clone repository
git clone https://github.com/akougkas/helios-mcp
cd helios-mcp

# Install dependencies
uv sync

# Run tests
uv run pytest

# Build package
uv build
```

## Troubleshooting

### MCP Connection Issues
```bash
# Verify installation
helios-mcp --version

# Test with verbose logging
uvx helios-mcp --verbose

# Check configuration directory
ls -la ~/.helios/
```

### Common Solutions

| Issue | Solution |
|-------|----------|
| "Tool not found" | Ensure helios-mcp is in PATH or use full path |
| "Git error" | Helios auto-initializes git in config directory |
| "Permission denied" | Check write permissions for `~/.helios/` |
| "No personas found" | Create at least one `.yaml` file in `~/.helios/personas/` |

## Why Helios?

Unlike traditional configuration management:

1. **Mathematical Precision** - Not JSON merging, but weighted inheritance
2. **Evolutionary** - Behaviors improve over time through Git versioning
3. **Domain-Aware** - Different personalities for different contexts
4. **Privacy-First** - Everything stays local, no cloud dependencies
5. **MCP Native** - Built specifically for the Model Context Protocol

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) first.

```bash
# Fork, clone, and create a feature branch
git checkout -b feature/amazing-feature

# Make changes and test
uv run pytest

# Commit and push
git commit -m "Add amazing feature"
git push origin feature/amazing-feature
```

## License

MIT © 2025 Anthony Kougkas

---

**Ready to give your AI a persistent personality?**

```bash
uvx helios-mcp
```

Built with ☀️ for the MCP ecosystem