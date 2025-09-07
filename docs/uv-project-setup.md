# UV 0.8.15+ Project Setup & FastMCP Integration
**Updated**: 2025-09-07
**Version**: UV 0.8.15+, FastMCP 2.2.6
**Source**: Official docs, GitHub issues, community guides

## Quick Reference

### Essential UV Commands
```bash
# For existing projects (DO NOT use uv init - it fails)
uv sync                    # Install deps from pyproject.toml
uv add fastmcp>=2.2.6     # Add new dependency
uv add pytest --dev       # Add dev dependency
uv run python main.py     # Run with deps
uv run pytest             # Run tests
```

### FastMCP Minimal Server
```python
from fastmcp import FastMCP

mcp = FastMCP("Helios")

@mcp.tool()
def get_config(persona: str) -> dict:
    """Get persona configuration with inheritance."""
    return {"persona": persona, "config": {}}

if __name__ == "__main__":
    mcp.run()
```

## UV 0.8.15+ Behavior Details

### 1. `uv init` with Existing pyproject.toml
**CRITICAL**: If there's already a `pyproject.toml` file, `uv init` will **exit with an error**. This is intentional behavior to prevent overwriting existing project configuration.

**Solution for Existing Projects:**
- Use `uv sync` to install dependencies from existing pyproject.toml
- Use `uv add <package>` to add new dependencies
- Manually configure pyproject.toml if needed

### 2. UV Command Arguments
```bash
# Project initialization (only for NEW projects)
uv init example             # Creates new project
uv init --bare             # Minimal pyproject.toml without sample code

# Working with existing projects
uv sync                    # Install all dependencies
uv sync --no-dev          # Skip dev dependencies
uv add package            # Add to [dependencies]
uv add package --dev      # Add to [dependency-groups.dev]
uv add package==1.2.3     # Specific version
uv add -r requirements.txt # From requirements file

# Running code
uv run python script.py    # Run with environment
uv run --with requests script.py  # Temporary dependency
```

### 3. Existing vs New Project Handling
- **New Projects**: `uv init` creates pyproject.toml + sample code + uv.lock
- **Existing Projects**: Use `uv sync` to install deps, `uv add` to modify deps
- **Migration**: UV works with setup.py projects - can add pyproject.toml alongside

### 4. uv.toml vs pyproject.toml Relationship

#### Use pyproject.toml [tool.uv] for:
- Project-specific UV settings
- Single source of truth approach
- Standard Python projects

#### Use uv.toml for:
- User-level config: `~/.config/uv/uv.toml`
- System-level config: `/etc/uv/uv.toml`
- Override project settings (takes precedence)

**Configuration Priority:**
1. Command-line args
2. Environment variables  
3. Project uv.toml
4. Project pyproject.toml [tool.uv]
5. User uv.toml
6. System uv.toml

### 5. Dependency Sync/Install Commands
```bash
# Install project dependencies
uv sync                    # All deps including dev
uv sync --no-dev          # Production only
uv sync --frozen          # Use exact lockfile versions

# Add dependencies
uv add requests           # Runtime dependency
uv add pytest --dev      # Development dependency
uv add "fastapi>=0.68.0"  # Version constraint

# Lock dependencies
uv lock                   # Update uv.lock file
uv lock --frozen         # Don't update existing pins
```

## FastMCP 2.2.6 Setup

### 6. Minimal Server with Decorators
```python
from fastmcp import FastMCP
from pydantic import BaseModel
from typing import Dict, Any

# Initialize server
mcp = FastMCP("Helios MCP Server")

# Simple tool
@mcp.tool()
def get_base_config() -> Dict[str, Any]:
    """Get base configuration for persona inheritance."""
    return {
        "base_importance": 0.8,
        "specialization_level": 1.0,
        "behaviors": {
            "communication_style": "technical",
            "response_format": "structured"
        }
    }

# Tool with complex input
class PersonaRequest(BaseModel):
    persona: str
    merge_base: bool = True

@mcp.tool()
def get_persona_config(request: PersonaRequest) -> Dict[str, Any]:
    """Get persona configuration with optional base merging."""
    config = {"persona": request.persona}
    if request.merge_base:
        base = get_base_config()
        # Inheritance calculation here
    return config

# Resource example
@mcp.resource("helios://personas/{persona_name}")
def get_persona_resource(persona_name: str) -> str:
    """Get persona YAML configuration as resource."""
    return f"# Configuration for {persona_name}\nbase_importance: 0.8"

if __name__ == "__main__":
    mcp.run()
```

### 7. FastMCP Project Structure for Packaging
```
helios-mcp/
├── src/
│   └── helios_mcp/
│       ├── __init__.py
│       ├── server.py      # FastMCP server
│       ├── models.py      # Pydantic models
│       └── config/
│           ├── __init__.py
│           └── loader.py  # Configuration loading
├── tests/
│   ├── test_server.py
│   └── test_config.py
├── pyproject.toml
└── README.md
```

**pyproject.toml for FastMCP:**
```toml
[project]
name = "helios-mcp"
version = "0.1.0"
dependencies = [
    "fastmcp>=2.2.6",
    "pyyaml>=6.0",
    "gitpython>=3.1.0",
]

[project.scripts]
helios-mcp = "helios_mcp.server:main"

[project.entry-points.mcp_servers]
helios = "helios_mcp.server:create_server"

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
]
```

## Advanced Patterns

### FastMCP with Context Injection
```python
from fastmcp import FastMCP, Context

@mcp.tool()
async def calculate_inheritance(
    persona: str, 
    ctx: Context
) -> Dict[str, float]:
    """Calculate inheritance weights with request context."""
    # Access request context if needed
    user_id = ctx.get("user_id", "anonymous")
    
    # Your inheritance calculation
    base_importance = 0.8
    specialization_level = 2.0
    weight = base_importance / (specialization_level ** 2)
    
    return {
        "inheritance_weight": weight,
        "calculated_for": user_id
    }
```

### UV Workflow Integration
```bash
# Development workflow
uv add fastmcp>=2.2.6      # Add FastMCP
uv add pyyaml gitpython    # Add other deps
uv add pytest ruff --dev  # Add dev tools

# Run during development
uv run python -m helios_mcp.server  # Start server
uv run pytest                       # Run tests
uv run ruff check .                 # Lint code

# Build and publish
uv build                    # Build wheel/sdist
uv publish                  # Publish to PyPI
```

## Common Issues & Solutions

### Issue: `uv init` fails with existing pyproject.toml
**Solution**: Don't use `uv init`. Use `uv sync` for existing projects.

### Issue: FastMCP tools not registering
**Solution**: Ensure proper decorator usage and server.run() call:
```python
@mcp.tool()  # Not @mcp.tool - needs parentheses
def my_tool() -> str:
    return "works"
```

### Issue: Dependencies not installing
**Solution**: Check that pyproject.toml has proper structure:
```toml
[project]
dependencies = [
    "fastmcp>=2.2.6",  # Runtime deps here
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",  # Dev deps here
]
```

### Issue: Entry point not found after install
**Solution**: Use proper entry point format in pyproject.toml:
```toml
[project.scripts]
helios-mcp = "helios_mcp.server:main"  # module:function
```

## Performance Notes

- UV is ~20x faster than pip for most operations
- FastMCP 2.2.6 includes significant performance improvements
- Use `uv sync --frozen` in CI/CD for reproducible builds
- Leverage UV's caching - repeated installs are near-instant

## Version Requirements

- **Python**: >=3.13 (for Helios project)
- **UV**: >=0.8.15 (latest stable)  
- **FastMCP**: >=2.2.6 (decorator support)
- **PyYAML**: >=6.0 (YAML 1.2 support)
- **GitPython**: >=3.1.0 (modern Git operations)

## Next Steps for Helios

1. Use `uv sync` to install existing dependencies
2. Create minimal FastMCP server with base config tool
3. Add inheritance calculation logic
4. Test with UV workflow: `uv run python -m helios_mcp.server`
5. Package and publish: `uv build && uv publish`