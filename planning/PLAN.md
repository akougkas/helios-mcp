# Implementation Roadmap

**CRITICAL INSTRUCTION FOR CODING AI**: This is a UV-EXCLUSIVE project. NEVER use pip, python, or any other package manager. ONLY use uv commands. This is non-negotiable.

## Phase 1: Foundation (Week 1)

### Core FastMCP Server
```python
# Initial server structure - FastMCP 2.2.6+ (September 2025)
from fastmcp import FastMCP
from pathlib import Path
import yaml
import git
from typing import Optional
from pydantic import Field

mcp = FastMCP(
    name="Helios 🌞",
    version="0.1.0",
    description="AI Behavior Solar System - MCP Server"
)

# Core configuration management
HELIOS_HOME = Path("~/.helios").expanduser()
```

### Essential Tools
Implement 5 fundamental MCP tools using FastMCP 2.2.6+ decorators:
```python
@mcp.tool(
    description="Retrieve base behavioral configuration from solar core",
    tags={"core", "identity"}
)
async def get_core_identity() -> dict:
    """Retrieve base behavioral configuration"""
    # Implementation follows

@mcp.tool(
    description="Load appropriate persona based on task context",
    tags={"persona", "context"}
)
async def get_active_persona(
    context: dict = Field(description="Current task context and requirements")
) -> dict:
    """Load appropriate persona for context"""
    # Implementation follows

@mcp.tool(
    description="Update and persist user preferences",
    tags={"preferences", "persistence"}
)
async def update_preference(
    domain: str = Field(description="Preference domain (e.g., 'coding', 'research')"),
    key: str = Field(description="Preference key"),
    value: str = Field(description="New preference value")
) -> bool:
    """Persist user preferences"""
    # Implementation follows

@mcp.tool(
    description="Search for learned behavioral patterns",
    tags={"patterns", "learning"}
)
async def search_patterns(
    query: str = Field(description="Pattern search query"),
    confidence_min: float = Field(default=0.7, description="Minimum confidence threshold")
) -> list:
    """Find learned behaviors matching query"""
    # Implementation follows

@mcp.tool(
    description="Commit behavioral changes to git repository",
    tags={"git", "versioning"}
)
async def commit_changes(
    message: str = Field(description="Git commit message")
) -> str:
    """Git commit behavioral changes"""
    # Implementation follows
```

### Templates
Create starter templates in YAML:
- `templates/researcher/` - Your use case
- `templates/engineer/` - Software development  
- `templates/creative/` - Writing and creative work
- `templates/base/` - Minimal starter

## Phase 2: Orbital Mechanics (Week 2)

### Gravitational Model
```python
from fastmcp import Context

@mcp.tool(
    description="Calculate behavioral influence based on orbital mechanics",
    tags={"orbital", "calculation"},
    annotations={"idempotentHint": True}
)
async def calculate_behavior(
    persona: str = Field(description="Active persona identifier"), 
    task_context: dict = Field(description="Current task requirements"),
    ctx: Context = None  # Context injection for logging/progress
) -> dict:
    """
    Apply gravitational inheritance:
    influence = core_mass / (orbital_distance ** 2)
    """
    if ctx:
        await ctx.info(f"Calculating behavior for {persona}")
    # Implementation follows
```

### Learning Engine
```python
@mcp.tool(
    description="Record behavioral patterns for learning",
    tags={"learning", "patterns"},
    annotations={"destructiveHint": False}
)
async def record_pattern(
    pattern: dict = Field(description="Behavioral pattern to record"),
    success: bool = Field(description="Whether pattern was successful"),
    ctx: Context = None
) -> bool:
    """Track behavioral patterns for resonance detection"""
    if ctx:
        await ctx.progress("Recording pattern", 0.5)
    # Implementation follows

@mcp.tool(
    description="Check if pattern has achieved orbital stability",
    tags={"resonance", "stability"},
    annotations={"readOnlyHint": True, "idempotentHint": True}
)
async def check_resonance(
    pattern_id: str = Field(description="Pattern identifier to check")
) -> dict:
    """Determine if pattern has achieved orbital stability"""
    # Implementation follows
```

## Phase 3: Evolution Features (Week 3)

### Self-Improvement Protocol
```python
@mcp.tool(
    description="Propose behavioral adaptations based on observations",
    tags={"evolution", "adaptation"},
    meta={"version": "1.0", "requires_approval": True}
)
async def propose_adaptation(
    observation: str = Field(description="Observed pattern or issue"),
    current_behavior: str = Field(description="Current behavioral response"),
    proposed_change: str = Field(description="Suggested behavioral adaptation"),
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in proposed change")
) -> dict:
    """Agent-initiated behavioral refinement"""
    # Implementation follows
```

### Transient Behaviors
```python
@mcp.tool(
    description="Inject temporary behavioral modifications",
    tags={"transient", "temporary"},
    annotations={"destructiveHint": False}
)
async def inject_transient(
    behavior: dict = Field(description="Temporary behavior specification"),
    duration: str = Field(description="Duration (e.g., '1h', '7d', 'session')"),
    trigger: dict = Field(description="Activation trigger conditions")
) -> str:
    """Add temporary behavioral modification (asteroid/comet)"""
    # Implementation follows
```

## Phase 4: Polish & Release (Week 4)

### UV-Based Installation (UV 0.8.15+ - September 2025)
```bash
# Initialize uv project structure with Python 3.13
uv init --python 3.13
uv sync --all-extras

# Build distribution with uv_build backend
uv build

# Publish to PyPI with authentication
uv publish --index pypi

# Users install with uv tool
uv tool install helios-mcp
# OR add to their project
uv add helios-mcp

# For development
uv sync --dev
uv run --with ipython python
```

### Installation Script (install.sh)
```bash
#!/bin/bash
# Helios MCP Installation - UV 0.8.15+ ONLY (September 2025)

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Installing uv 0.8.15+ (required)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Verify uv version
UV_VERSION=$(uv --version | cut -d' ' -f2)
echo "Found uv version: $UV_VERSION"

# Install Python 3.13 if needed
echo "Ensuring Python 3.13..."
uv python install 3.13

# Install Helios as a uv tool
echo "Installing Helios MCP with uv..."
uv tool install helios-mcp --python 3.13

# Initialize configuration
uvx helios init

echo "✅ Helios installed! Start with: uvx helios serve"
```

### Obsidian Integration
```python
@mcp.resource("vault://{note_path}")
async def read_vault_note(note_path: str) -> str:
    """Read note from Obsidian vault"""
    # Implementation follows

@mcp.tool(
    description="Synchronize with Obsidian vault",
    tags={"obsidian", "sync"}
)
async def sync_with_vault(
    vault_path: str = Field(description="Path to Obsidian vault")
) -> bool:
    """Bridge to existing Obsidian memory system"""
    # Implementation follows
```

## Technical Stack - UV EXCLUSIVE (September 2025)

### Core Dependencies (pyproject.toml)
```toml
[project]
name = "helios-mcp"
version = "0.1.0"
description = "AI Behavior Solar System - MCP Server"
readme = "README.md"
requires-python = ">=3.13"
license = "MIT"
authors = [
    { name = "Your Name", email = "your.email@example.com" }
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3.13",
    "Framework :: FastMCP",
]
dependencies = [
    "fastmcp>=2.2.6",       # Latest FastMCP 2.2.6+ (September 2025)
    "mcp>=1.9.2,<2.0.0",    # MCP Protocol 2025-06-18 spec
    "pyyaml>=6.0.2",        # YAML configuration
    "gitpython>=3.1.43",    # Git integration
    "pydantic>=2.9.0",      # Data validation
    "rich>=13.8.0",         # Beautiful CLI output
    "typer>=0.12.5",        # CLI framework
    "httpx>=0.27.2",        # HTTP client for auth
    "python-dotenv>=1.0.1", # Environment management
]

[project.scripts]
helios = "helios.cli:main"
helios-serve = "helios.server:serve"

[dependency-groups]
dev = [
    "pytest>=8.3.3",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.6.8",
    "mypy>=1.11.2",
    "ipython>=8.27.0",
    "pre-commit>=3.8.0",
]

[build-system]
requires = ["uv_build>=0.8.11,<0.9.0"]
build-backend = "uv_build"

[tool.uv]
package = true
managed = true

[[tool.uv.index]]
url = "https://pypi.org/simple"
default = true

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.mypy]
python_version = "3.13"
strict = true
```

### Development Tools - UV 0.8.15+ COMMANDS ONLY (September 2025)
- `uv sync` - Install/update all dependencies
- `uv sync --dev` - Include development dependencies
- `uv run pytest` - Run tests with pytest
- `uv run pytest --cov` - Run tests with coverage
- `uv run ruff check .` - Lint code with ruff
- `uv run ruff format .` - Format code
- `uv run mypy .` - Type checking
- `uv run helios serve` - Start MCP server
- `uv run --with ipython python` - Interactive Python with IPython
- `uv build` - Build distribution packages
- `uv publish --index pypi` - Publish to PyPI
- `uvx helios-mcp` - Run as global tool
- `uv pip list` - List installed packages
- `uv tree` - Show dependency tree
- `uv tree --show-sizes` - Show package sizes

### FORBIDDEN COMMANDS (NEVER USE)
- ❌ `pip install` - NEVER - Use `uv add` or `uv pip install`
- ❌ `python script.py` - Use `uv run script.py`
- ❌ `pip freeze` - Use `uv pip list` or `uv tree`
- ❌ `virtualenv` or `venv` - UV manages environments automatically
- ❌ `poetry` - This is a UV-exclusive project
- ❌ `conda` or `mamba` - UV handles Python installation
- ❌ `pipx` - Use `uv tool install` instead
- ❌ `pyenv` - Use `uv python install` instead

## Success Criteria

### Week 1: Foundation
✓ FastMCP server running with 5 core tools  
✓ Git integration working  
✓ Basic YAML configuration loading  
✓ One complete template

### Week 2: Orbital Mechanics  
✓ Gravitational inheritance functional  
✓ Pattern detection working  
✓ Multiple personas loadable  
✓ Behavioral merging correct

### Week 3: Evolution
✓ Self-improvement proposals generated  
✓ Transient behaviors functional  
✓ Confidence scoring operational  
✓ Cross-agent learning possible

### Week 4: Release
✓ PyPI package published  
✓ Installation < 5 minutes  
✓ Documentation complete  
✓ 3+ example configurations

---

# README.md

