# README Design Document for Helios MCP

## Overview

This document outlines an enhanced README design for Helios MCP, inspired by Context7's successful patterns while maintaining our unique identity as a behavioral inheritance system for AI personalities.

## Design Principles

1. **Immediate Value Clarity**: Lead with the problem we solve
2. **Visual Impact**: Use the inheritance formula as our unique hook
3. **Professional Simplicity**: Clean, scannable, not overly technical
4. **Action-Oriented**: Get users running in < 2 minutes
5. **Technical Credibility**: Show the math, architecture, and Git integration

## Proposed Structure

### 1. Header Section

```markdown
# ☀️ Helios MCP

**Give your AI persistent personality through mathematical inheritance**

[![PyPI](https://img.shields.io/pypi/v/helios-mcp)](https://pypi.org/project/helios-mcp/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP 2025](https://img.shields.io/badge/MCP-2025--06--18-purple)](https://modelcontextprotocol.io/)
```

**Changes from current:**
- Stronger tagline focusing on the core value prop
- Consistent badge styling with Context7

### 2. Value Proposition (The "Without vs With" Pattern)

```markdown
## The Problem

### Without Helios
- 🔄 **Stateless AI** - Every conversation starts from zero
- 📝 **Manual prompts** - Repeat preferences in every session
- 🎭 **No specialization** - Same personality for coding and writing
- 💾 **No memory** - Learned patterns disappear

### With Helios
- 🧬 **Evolving personality** - AI remembers and adapts
- ⚖️ **Mathematical inheritance** - Precise control over specialization
- 🎯 **Domain personas** - Different personalities for different tasks
- 📊 **Git-versioned evolution** - Track behavioral changes over time
```

**New addition** - This clear contrast helps users immediately understand the value.

### 3. The Hook - Our Unique Formula

```markdown
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
```

**Enhancement** - Make the formula the star, with immediate practical example.

### 4. Quick Start (Context7 Style)

```markdown
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
      "args": ["helios-mcp"]
    }
  }
}
```

### VS Code
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
```

**Improvement** - Multiple IDE configs like Context7, cleaner formatting.

### 5. Live Example (Show, Don't Tell)

```markdown
## See It In Action

```python
# Your base configuration defines core identity
base_config = {
    "communication": "Direct and technical",
    "values": ["User sovereignty", "Ship working code"],
    "base_importance": 0.7
}

# Specialized persona for code review
code_reviewer = {
    "focus": "Security and performance",
    "specialization_level": 2
}

# Helios calculates: 0.7 / (2²) = 0.175 base weight
# Result: 17.5% base personality + 82.5% reviewer expertise
# You get: Security-focused reviewer who still ships pragmatically
```
```

**New section** - Concrete example showing inheritance in action.

### 6. Available Tools (Simplified Table)

```markdown
## MCP Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `get_base_config` | Load foundation identity | Core behaviors, values |
| `get_active_persona` | Retrieve specialization | Domain-specific focus |
| `merge_behaviors` | **Calculate inheritance** | Real-time synthesis |
| `update_preference` | Learn from interactions | Adapt over time |
| `commit_changes` | Version with Git | Track evolution |
```

**Simplification** - Single table, focused on purpose rather than technical details.

### 7. Architecture (Visual ASCII)

```markdown
## How It Works

```
     Base Identity           Personas              Active Behavior
    ┌─────────────┐      ┌─────────────┐        ┌──────────────┐
    │ Foundation  │ ───► │ Specialized │ ────►  │   Weighted   │
    │  Behaviors  │      │  Overrides  │        │    Merge     │
    └─────────────┘      └─────────────┘        └──────────────┘
           0.7                  2.0              17.5% + 82.5%
     (base_importance)  (specialization_level)   (inheritance)
                                │
                                ▼
                         Git Versioning
                      Every change tracked
```
```

**Enhancement** - Simpler, more visual architecture diagram.

### 8. Common Use Cases

```markdown
## Use Cases

### Multi-Domain Assistant
```yaml
personas/
├── researcher.yaml    # Academic writing, citations
├── coder.yaml        # Type-safe, test-driven
└── reviewer.yaml     # Security-focused, thorough
```

### Learning System
```yaml
learned/
├── user_preferences.yaml    # "Always use UV, never pip"
├── code_patterns.yaml       # "Prefer async/await"
└── communication.yaml       # "Be more concise"
```
```

**New section** - Practical examples users can relate to.

### 9. Troubleshooting (Context7 Style)

```markdown
## Troubleshooting

### Helios not appearing in Claude Desktop?
- Check UV is installed: `uv --version`
- Verify config path: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Restart Claude Desktop after config changes

### Inheritance not working as expected?
- Higher `base_importance` = stronger foundation (0.5-0.9)
- Lower `specialization_level` = more inheritance (1-5)
- Check formula: `weight = base_importance / (specialization_level²)`

### Changes not persisting?
- Ensure Git is initialized: `cd ~/.helios && git init`
- Check write permissions: `ls -la ~/.helios`
```

**Addition** - Professional troubleshooting section like Context7.

### 10. Footer (Clean Credits)

```markdown
---

## Philosophy

> "The sun doesn't need to be perfect to shine." ☀️

Helios believes in mathematical precision for behavioral evolution. Not another RAG system or knowledge base - pure personality management through weighted inheritance.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT © 2025

---

Built with [FastMCP](https://github.com/jlowin/fastmcp) • [Model Context Protocol](https://modelcontextprotocol.io/)
```

## Key Improvements Over Current README

1. **Stronger Opening**: Clear problem/solution contrast
2. **Formula as Hero**: Make our unique math the centerpiece
3. **Multiple IDE Support**: Not just Claude Desktop
4. **Live Examples**: Show actual inheritance calculations
5. **Simplified Tables**: One clean tools table
6. **Visual Architecture**: ASCII diagram with real numbers
7. **Use Cases Section**: Practical applications
8. **Professional Troubleshooting**: Common issues and solutions
9. **Cleaner Footer**: Philosophy + minimal credits

## Implementation Notes

- Keep total length under 500 lines for scannability
- Use consistent emoji sparingly (☀️ for branding)
- Include real numbers in examples (0.7, 2, 17.5%)
- Focus on behavioral management, not data storage
- Emphasize Git versioning as a key feature
- Make UV the primary installation method

## Metrics for Success

- User understands value in < 30 seconds
- Can install and run in < 2 minutes
- Knows how inheritance works from examples
- Has clear troubleshooting path
- Feels professional and technically credible

## Next Steps

1. Implement this design in README.md
2. Add example configurations in `samples/` directory
3. Create GitHub badges if repo is public
4. Consider adding a GIF demo of inheritance calculation
5. Add star history when project gains traction