# Helios MCP Architecture Review

## Executive Summary

This document reviews the current Helios MCP implementation and identifies critical issues preventing production deployment. The server has fundamental async/await issues, lacks proper CLI support, and needs restructuring for FastMCP best practices.

## Critical Issues to Fix

### 1. Async/Await Violations

**Issue**: Line 553 in `server.py` calls `mcp.list_tools()` synchronously in an async context
```python
# CURRENT (broken):
logger.info(f"Helios MCP Server ready with {len(mcp.list_tools())} tools")

# FIXED:
# Remove this line entirely - FastMCP doesn't expose tool count
logger.info("Helios MCP Server ready")
```

**Issue**: Line 202 references undefined `inheritance_weight` variable
```python
# CURRENT (broken):
"inheritance_weight": inheritance_weight,  # Not defined!

# FIXED:
"inheritance_weight": merger.inheritance_weight,
```

### 2. Missing CLI Interface

**Current State**: 
- Entry point calls `asyncio.run(main())` directly
- No argument parsing for `--helios-dir`
- Not compatible with `uvx helios-mcp` patterns

**Required CLI Structure**:
```python
# src/helios_mcp/cli.py (NEW FILE)
import argparse
import asyncio
from pathlib import Path
from typing import Optional
from .server import create_server

def parse_args():
    parser = argparse.ArgumentParser(
        description="Helios MCP Server - AI behavior configuration"
    )
    parser.add_argument(
        "--helios-dir",
        type=Path,
        default=Path.home() / ".helios",
        help="Path to Helios configuration directory"
    )
    return parser.parse_args()

def main():
    """CLI entry point for uvx/uv tool compatibility."""
    args = parse_args()
    asyncio.run(run_server(args.helios_dir))

async def run_server(helios_dir: Path):
    server = create_server(helios_dir)
    await server.run()
```

### 3. Server Structure Issues

**Current Problems**:
- Global state variables (config, loader, git_store)
- No factory function for creating server instances
- Hard-coded paths instead of configurable

**Recommended Refactor**:
```python
# src/helios_mcp/server.py (refactored structure)
def create_server(helios_dir: Optional[Path] = None) -> FastMCP:
    """Factory function to create configured MCP server."""
    # Initialize configuration with custom directory
    config = HeliosConfig(base_path=helios_dir or Path.home() / ".helios")
    loader = ConfigLoader(config)
    git_store = GitStore(config.base_path.parent)
    
    # Create MCP instance
    mcp = FastMCP("Helios")
    
    # Register tools with closure over config/loader/git_store
    # (tools access these via closure, not global state)
    
    return mcp
```

### 4. Entry Point Configuration

**Current pyproject.toml**:
```toml
[project.scripts]
helios-mcp = "helios_mcp.server:main"  # Points to async function
```

**Required Update**:
```toml
[project.scripts]
helios-mcp = "helios_mcp.cli:main"  # Points to sync CLI handler
```

## Recommended File Structure

```
src/helios_mcp/
├── __init__.py       # Export main components
├── cli.py           # NEW: CLI argument handling
├── server.py        # Refactored with create_server()
├── config.py        # Existing, add path configuration
├── inheritance.py   # Existing, working correctly
└── git_store.py     # Existing, working correctly
```

## Implementation Plan

### Phase 1: Fix Critical Bugs (30 minutes)
1. Remove `mcp.list_tools()` call (line 553)
2. Fix undefined `inheritance_weight` (line 202)
3. Test basic server startup

### Phase 2: Add CLI Interface (45 minutes)
1. Create `cli.py` with argument parsing
2. Refactor `server.py` to use factory pattern
3. Update `pyproject.toml` entry point
4. Test `uvx helios-mcp --helios-dir /custom/path`

### Phase 3: Refactor for Production (45 minutes)
1. Eliminate global state variables
2. Use dependency injection pattern
3. Add proper error handling for missing config
4. Ensure Claude Desktop compatibility

### Phase 4: Testing & Documentation (30 minutes)
1. Test with Claude Desktop configuration
2. Verify MCP stdio protocol compliance
3. Update README with usage examples

## Claude Desktop Integration

**Required mcpServers Configuration**:
```json
{
  "helios": {
    "command": "uvx",
    "args": ["helios-mcp", "--helios-dir", "/home/user/.helios"],
    "env": {}
  }
}
```

## FastMCP Best Practices

### 1. Server Initialization
- Use factory functions, not global state
- Pass configuration via constructor/factory
- Keep server creation separate from running

### 2. Tool Registration
- Tools should be pure functions when possible
- Use Context for logging, not print statements
- Return structured dictionaries consistently

### 3. Async Patterns
- FastMCP handles async internally
- Don't mix sync/async inappropriately
- Server.run() is the main async entry point

### 4. Error Handling
- Always return status dictionaries from tools
- Log errors with proper logger
- Provide fallback behavior for missing config

## Testing Checklist

- [ ] Server starts without errors
- [ ] `uvx helios-mcp` works from command line
- [ ] `uvx helios-mcp --helios-dir /tmp/test` uses custom directory
- [ ] Claude Desktop can connect to server
- [ ] All tools are discoverable by MCP clients
- [ ] Git operations work correctly
- [ ] Inheritance calculations are accurate
- [ ] YAML files load/save properly

## Security Considerations

1. **Path Traversal**: Validate all file paths stay within helios_dir
2. **Git Operations**: Only commit within helios repository
3. **YAML Loading**: Use safe_load to prevent code injection
4. **File Permissions**: Respect OS-level file permissions

## Performance Optimizations

1. **Lazy Loading**: Don't load all personas on startup
2. **Caching**: Cache loaded YAML files with modification time checks
3. **Async I/O**: Use aiofiles for file operations
4. **Git Operations**: Consider gitpython async alternatives

## Conclusion

The Helios MCP server has a solid foundation but needs critical fixes for production use:

1. **Immediate**: Fix async/await bugs preventing startup
2. **Required**: Add CLI interface for uvx compatibility  
3. **Important**: Refactor to eliminate global state
4. **Future**: Add caching and performance optimizations

With these changes, Helios will be ready for PyPI publication and production use with Claude Desktop.