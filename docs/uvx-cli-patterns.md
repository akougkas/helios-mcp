# UVX CLI Patterns for MCP Servers
**Updated**: 2025-09-07
**Version**: UV 0.8.15+, FastMCP 2.2.6
**Source**: Official docs, GitHub examples, community guides

## Quick Reference

### uvx vs uv Commands
```bash
# uvx (tool execution - for installed packages)
uvx helios-mcp --helios-dir ~/.helios
uvx mcp-server-time --local-timezone UTC

# uv tool (for development/local projects)  
uv tool install helios-mcp
uv run python -m helios_mcp.server
```

### Claude Desktop mcpServers Configuration
```json
{
  "mcpServers": {
    "helios": {
      "command": "uvx",
      "args": ["helios-mcp", "--helios-dir", "/Users/username/.helios"]
    }
  }
}
```

## Entry Point Definition Patterns

### 1. pyproject.toml Configuration
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "helios-mcp"
version = "0.1.0"
description = "Configuration management system for AI behaviors"
requires-python = ">=3.13"
dependencies = [
    "fastmcp>=2.2.6",
    "pyyaml>=6.0",
    "gitpython>=3.1.0",
    "click>=8.1.0",
]

# THIS IS THE KEY: CLI entry points
[project.scripts]
helios-mcp = "helios_mcp.cli:main"

# Optional: MCP server entry points
[project.entry-points.mcp_servers]
helios = "helios_mcp.server:create_server"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
]
```

### 2. CLI Module Structure (helios_mcp/cli.py)
```python
"""CLI interface for Helios MCP server."""

import sys
import click
import asyncio
from pathlib import Path
from .server import create_server

@click.command()
@click.option(
    "--helios-dir",
    default=lambda: Path.home() / ".helios",
    type=click.Path(path_type=Path),
    help="Directory for Helios configurations"
)
@click.option(
    "--port",
    default=3000,
    type=int,
    help="Port to run the server on"
)
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio", "sse"]),
    help="Transport method for MCP server"
)
def main(helios_dir: Path, port: int, transport: str) -> int:
    """Start Helios MCP server."""
    try:
        helios_dir.mkdir(parents=True, exist_ok=True)
        
        # Create and run the FastMCP server
        server = create_server(helios_dir)
        
        if transport == "stdio":
            server.run()
        else:
            # For SSE transport
            server.run_sse(port=port)
            
        return 0
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return 1

# CRITICAL: This makes uvx work correctly
if __name__ == "__main__":
    sys.exit(main())
```

### 3. FastMCP Server Factory (helios_mcp/server.py)
```python
"""FastMCP server implementation for Helios."""

from pathlib import Path
from typing import Dict, Any
from fastmcp import FastMCP
import yaml

def create_server(helios_dir: Path = None) -> FastMCP:
    """Create FastMCP server instance."""
    if helios_dir is None:
        helios_dir = Path.home() / ".helios"
    
    # Initialize server
    mcp = FastMCP("Helios Configuration Manager")
    
    @mcp.tool()
    def get_base_config() -> Dict[str, Any]:
        """Get base configuration for persona inheritance."""
        base_file = helios_dir / "base" / "config.yaml"
        if base_file.exists():
            with base_file.open() as f:
                return yaml.safe_load(f)
        return {
            "base_importance": 0.8,
            "specialization_level": 1.0,
            "behaviors": {
                "communication_style": "technical",
                "response_format": "structured"
            }
        }
    
    @mcp.tool()
    def get_persona_config(persona: str) -> Dict[str, Any]:
        """Get persona configuration with inheritance."""
        persona_file = helios_dir / "personas" / f"{persona}.yaml"
        if persona_file.exists():
            with persona_file.open() as f:
                return yaml.safe_load(f)
        return {"error": f"Persona '{persona}' not found"}
    
    @mcp.resource("helios://personas/{persona_name}")
    def get_persona_resource(persona_name: str) -> str:
        """Get persona configuration as resource."""
        config = get_persona_config(persona_name)
        return yaml.dump(config, default_flow_style=False)
    
    return mcp

# For direct execution during development
if __name__ == "__main__":
    server = create_server()
    server.run()
```

## Installation and Usage Patterns

### 1. Local Development
```bash
# Install dependencies
uv sync

# Run during development
uv run python -m helios_mcp.cli --helios-dir ~/.helios

# Or run server directly
uv run python -m helios_mcp.server
```

### 2. Package Installation
```bash
# Build package
uv build

# Install as tool (recommended for uvx usage)
uv tool install dist/helios_mcp-0.1.0-py3-none-any.whl

# Or install from PyPI
uv tool install helios-mcp
```

### 3. uvx Usage (End Users)
```bash
# Run directly with uvx
uvx helios-mcp --helios-dir ~/.helios

# With additional arguments
uvx helios-mcp --helios-dir /custom/path --transport sse --port 8080
```

## Claude Desktop Integration Patterns

### 1. Basic uvx Configuration
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

### 2. Custom Configuration Path
```json
{
  "mcpServers": {
    "helios-personal": {
      "command": "uvx", 
      "args": [
        "helios-mcp",
        "--helios-dir", "/Users/username/.helios-personal"
      ]
    }
  }
}
```

### 3. Development Server Configuration
```json
{
  "mcpServers": {
    "helios-dev": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/helios-mcp-dev",
        "python", "-m", "helios_mcp.cli"
      ]
    }
  }
}
```

### 4. With Environment Variables
```json
{
  "mcpServers": {
    "helios": {
      "command": "uvx",
      "args": ["helios-mcp", "--helios-dir", "${HELIOS_DIR:-~/.helios}"],
      "env": {
        "HELIOS_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## Command-Line Argument Patterns

### Using Click (Recommended)
```python
import click
from pathlib import Path

@click.command()
@click.option(
    "--helios-dir",
    default=lambda: Path.home() / ".helios",
    type=click.Path(path_type=Path),
    help="Configuration directory"
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.version_option(version="0.1.0")
def main(helios_dir: Path, verbose: bool) -> int:
    """Helios MCP server."""
    # Implementation here
    return 0
```

### Using argparse (Alternative)
```python
import argparse
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Helios MCP server")
    parser.add_argument(
        "--helios-dir",
        type=Path,
        default=Path.home() / ".helios",
        help="Configuration directory"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    # Implementation here
    return 0
```

## FastMCP Server Entry Point Patterns

### 1. Factory Function Pattern (Recommended)
```python
# server.py
def create_server() -> FastMCP:
    """Factory function for FastMCP server."""
    mcp = FastMCP("Server Name")
    
    @mcp.tool()
    def example_tool() -> str:
        return "Hello from tool"
    
    return mcp

# FastMCP CLI will call this automatically
# fastmcp run server.py:create_server
```

### 2. Module-Level Server Pattern
```python
# server.py
from fastmcp import FastMCP

# FastMCP looks for variables named: mcp, server, or app
mcp = FastMCP("Server Name")

@mcp.tool()
def example_tool() -> str:
    return "Hello from tool"

# FastMCP CLI will find this automatically
# fastmcp run server.py
```

### 3. Main Function Pattern (For Direct Execution)
```python
# server.py
def main():
    mcp = FastMCP("Server Name")
    
    @mcp.tool()
    def example_tool() -> str:
        return "Hello from tool"
    
    mcp.run()

if __name__ == "__main__":
    main()
```

## Common Issues and Solutions

### Issue: uvx command not found
**Solution**: Install uv first:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# or
pip install uv
```

### Issue: Entry point not found after installation
**Solution**: Ensure proper format in pyproject.toml:
```toml
[project.scripts]
helios-mcp = "helios_mcp.cli:main"  # module.submodule:function
```

### Issue: Claude Desktop can't find uvx
**Solution**: Use full path to uvx:
```json
{
  "mcpServers": {
    "helios": {
      "command": "/usr/local/bin/uvx",
      "args": ["helios-mcp"]
    }
  }
}
```

### Issue: Permission denied errors
**Solution**: Ensure proper directory permissions:
```python
# In CLI code
helios_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
```

### Issue: FastMCP tools not registering
**Solution**: Use proper decorator syntax:
```python
@mcp.tool()  # Needs parentheses
def my_tool() -> str:
    return "works"
```

## Testing Patterns

### 1. CLI Testing with Click
```python
from click.testing import CliRunner
from helios_mcp.cli import main

def test_cli_basic():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Helios MCP server" in result.output

def test_cli_custom_dir():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["--helios-dir", "./custom"])
        assert result.exit_code == 0
```

### 2. FastMCP Server Testing
```python
import pytest
from fastmcp.testing import TestClient
from helios_mcp.server import create_server

@pytest.fixture
def server():
    return create_server()

@pytest.fixture
def client(server):
    return TestClient(server)

def test_get_base_config(client):
    result = client.call_tool("get_base_config")
    assert result["base_importance"] == 0.8
```

## Performance Considerations

### uvx vs uv Startup Times
- **uvx**: ~100-300ms startup (cache hit)
- **uvx**: ~1-3s startup (cache miss)  
- **uv run**: ~50-100ms startup (local project)

### Memory Usage
- FastMCP server: ~15-30MB baseline
- With YAML configs: +5-10MB per 100 personas
- uvx overhead: ~5-10MB

### Recommendations
1. Use uvx for production deployment
2. Use `uv run` for development
3. Cache configurations in memory when possible
4. Use factory pattern for lazy initialization

## Version Requirements

- **Python**: >=3.13 (for Helios project)
- **UV**: >=0.8.15 (uvx stability improvements)
- **FastMCP**: >=2.2.6 (decorator support)
- **Click**: >=8.1.0 (modern CLI patterns)
- **PyYAML**: >=6.0 (YAML 1.2 support)

## Next Steps for Helios

1. Implement CLI module with Click
2. Create FastMCP server factory
3. Test uvx installation locally
4. Configure Claude Desktop integration
5. Publish to PyPI for uvx usage

## Example: Complete Helios Integration

### Directory Structure
```
helios-mcp/
├── src/helios_mcp/
│   ├── __init__.py
│   ├── cli.py          # uvx entry point
│   ├── server.py       # FastMCP server
│   └── config/
│       └── loader.py   # Configuration loading
├── pyproject.toml      # Entry points defined here
└── README.md
```

### Claude Desktop Configuration
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

### Installation and Usage
```bash
# Install
uv tool install helios-mcp

# Use directly
uvx helios-mcp --help

# Works in Claude Desktop automatically
```

This pattern ensures seamless uvx compatibility with proper CLI entry points, argument handling, and FastMCP server integration.