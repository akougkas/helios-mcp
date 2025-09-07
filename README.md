# Helios MCP 🌞

**The AI Behavior Configuration System** - Give your AI agents persistent personalities, learned behaviors, and evolving capabilities through a git-versioned behavioral management system.

> Built with FastMCP 2.2.6+ and UV 0.8.15+ for the MCP Protocol 2025-06-18 specification (September 2025)

## ⚠️ UV-EXCLUSIVE PROJECT

**This project uses ONLY Astral's UV package manager (0.8.15+). Do NOT use pip, poetry, conda, or any other Python package manager.**

## Prerequisites

### System Requirements
- Python 3.13 (recommended) or 3.12 (minimum)
- UV 0.8.15 or higher (September 2025)
- Git 2.40+
- macOS, Linux, or Windows 10/11

### Install UV
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify installation
uv --version  # Should show 0.8.15 or higher
```

## Installation

### As a UV Tool (Recommended)
```bash
# Install Python 3.13 if not present
uv python install 3.13

# Install Helios globally as a UV tool
uv tool install helios-mcp --python 3.13

# Run from anywhere
uvx helios init
uvx helios serve

# Or use the shorthand
uvx --from helios-mcp helios serve
```

### For Development
```bash
# Clone the repository
git clone https://github.com/yourusername/helios-mcp.git
cd helios-mcp

# Ensure Python 3.13
uv python pin 3.13

# Initialize UV project and sync all dependencies
uv sync --dev

# Run in development mode
uv run helios serve

# Run tests with coverage
uv run pytest --cov=helios

# Format and lint code
uv run ruff format .
uv run ruff check . --fix

# Type checking
uv run mypy src/helios
```

## The Inheritance Model

```yaml
# Your behavioral configuration hierarchy
base_config:  # Foundation configuration
  importance: 1.0
  behaviors: [identity, values, communication_style]

developer:  # Low specialization - coding persona
  specialization_level: 1.0
  inheritance_weight: 0.95  # 95% base influence
  specializes: [python, architecture, testing]

researcher:  # Higher specialization - knowledge persona
  specialization_level: 1.5
  inheritance_weight: 0.80  # 80% base influence
  specializes: [synthesis, organization, creativity]
```

## Usage with UV 0.8.15+

### Starting the MCP Server
```bash
# Using uvx (for installed tool)
uvx helios serve

# With specific Python version
uvx --python 3.13 helios serve

# Using uv run (for development)
uv run helios serve

# With environment variables
uv run --env-file .env helios serve

# With additional dependencies
uv run --with rich helios serve --verbose
```

### Configuration Commands
```bash
# Initialize with template
uvx helios init --template researcher

# Add a new persona with inheritance settings
uvx helios add-persona creative --specialization 2.0 --weight 0.6

# Learn a new pattern with confidence scoring
uvx helios learn "User prefers bullet points over paragraphs" --confidence 0.95

# Search patterns with minimum confidence
uvx helios search "communication style" --min-confidence 0.7

# Commit changes to git
uvx helios commit "Updated preferences"

# Sync with Obsidian vault
uvx helios sync-vault ~/Documents/ObsidianVault
```

## Development Workflow

```bash
# 1. Clone and enter directory
git clone <repo-url> && cd helios-mcp

# 2. Setup Python 3.13 environment
uv python install 3.13
uv python pin 3.13

# 3. Sync dependencies with UV
uv sync --dev --all-extras

# 4. Install pre-commit hooks
uv run pre-commit install

# 5. Make changes and test
uv run pytest tests/ -v --cov=helios

# 6. Format, lint, and type check
uv run ruff format .
uv run ruff check . --fix
uv run mypy src/helios

# 7. Build distribution with UV backend
uv build

# 8. Test locally
uv tool install --from dist/helios_mcp-*.whl --force --python 3.13

# 9. Publish to PyPI
uv publish --index pypi
```

## Project Structure

```
helios-mcp/
├── pyproject.toml      # UV project configuration (uv_build backend)
├── uv.toml             # UV-specific settings
├── .python-version     # Python 3.13 pinned
├── src/
│   └── helios/
│       ├── __init__.py
│       ├── server.py   # FastMCP 2.2.6+ server
│       ├── cli.py      # Typer CLI interface
│       ├── inheritance.py # Inheritance calculation engine
│       ├── tools.py    # MCP tool implementations
│       ├── resources.py # MCP resource templates
│       └── prompts.py  # Reusable prompt templates
├── tests/
│   ├── test_server.py
│   ├── test_tools.py
│   └── conftest.py
├── templates/          # Starter configurations
│   ├── researcher/
│   ├── engineer/
│   └── creative/
└── .pre-commit-config.yaml
```

## UV Scripts & Commands

The project includes several UV scripts and commands:

### Project Scripts (pyproject.toml)
```bash
# Defined in [project.scripts]
uv run helios serve     # Start MCP server
uv run helios init      # Initialize configuration
uv run helios status    # Check system status
uv run helios test      # Run test suite
```

### UV-Specific Commands
```bash
# Package management
uv add fastmcp          # Add dependency
uv remove package       # Remove dependency
uv tree --show-sizes    # Show dependency tree with sizes
uv pip list            # List installed packages

# Python management
uv python list         # List available Python versions
uv python install 3.13 # Install Python 3.13
uv python pin 3.13     # Pin project to Python 3.13

# Development
uv sync --dev          # Sync with dev dependencies
uv run --with ipython python  # Interactive shell
uv build              # Build distribution
uv publish            # Publish to PyPI
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. **Use UV 0.8.15+ for all operations** (no pip, poetry, or conda!)
4. Setup development environment:
   ```bash
   uv python pin 3.13
   uv sync --dev
   uv run pre-commit install
   ```
5. Make your changes and test:
   ```bash
   uv run pytest --cov=helios
   uv run ruff check .
   uv run mypy src/helios
   ```
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Submit a pull request

## Troubleshooting

### "Command not found: helios"
```bash
uv tool install helios-mcp --python 3.13
# Or use uvx directly:
uvx --from helios-mcp helios serve
```

### "No module named 'fastmcp'"
```bash
uv sync --dev  # Sync all dependencies
uv pip list    # Verify installation
```

### "Python version error"
```bash
uv python install 3.13  # Install Python 3.13
uv python pin 3.13      # Pin to project
uv sync --reinstall     # Reinstall dependencies
```

### "pip: command not found"
Good! This project doesn't use pip. Use `uv` instead:
- `uv add package` instead of `pip install`
- `uv pip list` instead of `pip list`
- `uv tree` instead of `pip freeze`

## Tech Stack

- **Python 3.13**: Latest stable with JIT compiler and free-threaded mode
- **UV 0.8.15+**: Ultra-fast Rust-based package manager (10-100x faster than pip)
- **FastMCP 2.2.6+**: Pythonic MCP server framework with decorators
- **MCP Protocol 2025-06-18**: Latest spec with OAuth 2.0, elicitation, structured output
- **Pydantic 2.9+**: Data validation and settings management
- **Rich 13.8+**: Beautiful terminal output and progress bars
- **Typer 0.12+**: Modern CLI framework

## License

MIT

---

**Built with [UV 0.8.15+](https://github.com/astral-sh/uv) and [FastMCP 2.2.6+](https://github.com/jlowin/fastmcp) for the [MCP Protocol 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)**
