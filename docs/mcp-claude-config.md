# MCP Server Configuration for Claude Desktop (2025)
**Updated**: 2025-09-07
**Version**: Claude Desktop 2025, FastMCP 2.2.6+
**Sources**: Official MCP docs, Claude Desktop docs, community guides

## Quick Reference
```json
{
  "mcpServers": {
    "server-name": {
      "command": "uvx",
      "args": ["--directory", "/absolute/path/to/server", "run", "server.py"],
      "env": {"LOG_LEVEL": "INFO"}
    }
  }
}
```

## Configuration File Location

### Claude Desktop
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json` 
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Claude Code CLI
- Uses separate configuration system
- Can use `/mcp add-json` commands
- Supports dynamic server addition

## FastMCP Server Structure

### Basic FastMCP Server
```python
from mcp.server.fastmcp import FastMCP
import logging

# Configure logging (CRITICAL - never use print()!)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Initialize server (name it 'mcp' for best compatibility)
mcp = FastMCP("server-name")

@mcp.tool()
def example_tool(param: str) -> str:
    """Tool description for Claude to understand."""
    logging.info(f"Processing: {param}")  # Use logging, NOT print!
    return f"Processed: {param}"

@mcp.resource("file://{path}")
def read_file(path: str) -> str:
    """Read file contents."""
    with open(path, 'r') as f:
        return f.read()

if __name__ == "__main__":
    mcp.run(transport='stdio')
```

## Configuration Patterns

### UV/UVX Command Structure
```json
{
  "mcpServers": {
    "helios": {
      "command": "uvx",
      "args": [
        "--directory", "/absolute/path/to/helios-mcp",
        "run", "helios_mcp/server.py"
      ],
      "env": {
        "LOG_LEVEL": "INFO",
        "HELIOS_CONFIG_PATH": "~/.helios"
      }
    }
  }
}
```

### Alternative UV Patterns
```json
{
  "mcpServers": {
    "helios-alt": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/absolute/path/to/helios-mcp",
        "python", "-m", "helios_mcp.server"
      ]
    }
  }
}
```

### Multiple Servers Configuration
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "~/Documents"]
    },
    "helios": {
      "command": "uvx",
      "args": ["--directory", "/path/to/helios", "run", "server.py"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "your-token"}
    }
  }
}
```

## Critical Requirements

### STDIO Protocol Rules
- **NEVER write to stdout** - corrupts JSON-RPC protocol
- Use `logging` instead of `print()`
- stderr is OK for debugging
- Claude Desktop uses stdio transport

### Logging Best Practices
```python
# ❌ WRONG - Breaks MCP protocol
print("Processing request")
console.log("Debug info")

# ✅ CORRECT - Safe for MCP
import logging
logging.info("Processing request")
logger = logging.getLogger(__name__)
logger.debug("Debug info")
```

### Server Requirements
- Python 3.10+ for FastMCP
- MCP SDK 1.2.0+
- Absolute paths in configuration
- Named `mcp` variable for best compatibility

## Common Issues and Solutions

### Connection Failures
```
Issue: Server fails to connect
Solutions:
1. Check absolute paths in configuration
2. Verify uvx vs npx usage (uvx for Python, npx for Node.js)
3. Restart Claude Desktop after config changes
4. Check logs at ~/Library/Logs/Claude/mcp-server-{name}.log
```

### Protocol Version Errors
```
Issue: protocolVersion validation errors
Solutions:
1. Ensure FastMCP server returns proper protocol version
2. Check for stdout contamination (print statements)
3. Verify JSON-RPC message format
```

### Keychain/Permission Issues (macOS)
```
Issue: "AbortError: The operation was aborted"
Solutions:
1. Grant Claude Desktop necessary permissions
2. Check macOS security settings
3. Try running server manually first
```

### Environment Variable Issues
```json
{
  "mcpServers": {
    "server": {
      "command": "uvx",
      "args": ["..."],
      "env": {
        "PYTHONPATH": "/path/to/modules",
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

## Verification and Testing

### Using Claude Code CLI
```bash
# Check server status
claude mcp list

# Add server dynamically  
claude mcp add-json helios '{"command":"uvx","args":["run","server.py"]}'

# Check connection status
/mcp  # Inside Claude Code interface
```

### Manual Testing
```bash
# Test server directly
cd /path/to/server
uvx run server.py

# Should show MCP protocol initialization
# No stdout output other than MCP messages
```

### MCP Inspector (Development)
- Browser-based testing tool
- Test tools, resources, prompts
- Verify server behavior before Claude integration

## Working Examples

### Minimal FastMCP Server
```python
#!/usr/bin/env python3
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("minimal")

@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

### Configuration for Above
```json
{
  "mcpServers": {
    "minimal": {
      "command": "uvx",
      "args": ["--directory", "/absolute/path/to/server", "run", "minimal.py"]
    }
  }
}
```

## Debug Checklist

Before troubleshooting MCP server issues:
- [ ] Using absolute paths in config?
- [ ] No print() statements in server code?
- [ ] Restarted Claude Desktop after config change?
- [ ] Server runs manually without errors?
- [ ] Using uvx for Python servers?
- [ ] Environment variables properly set?
- [ ] Checking logs at ~/Library/Logs/Claude/?

## Version Compatibility

### FastMCP 2.2.6+ Features
- Decorators: `@mcp.tool`, `@mcp.resource`, `@mcp.prompt`
- Context injection for request metadata
- Automatic tool schema generation
- Type hint validation

### MCP Protocol 2025-06-18
- OAuth 2.0 support
- Enhanced tool calling
- Structured output requirements
- Backward compatibility maintained

## Performance Notes

- FastMCP handles protocol details automatically
- Stdio transport has minimal overhead
- Multiple servers run in parallel
- Each server is isolated process
- Configure logging levels appropriately (INFO/WARN for production)

Remember: MCP servers extend Claude's capabilities through a standardized protocol. Keep servers focused, lightweight, and protocol-compliant for best results.