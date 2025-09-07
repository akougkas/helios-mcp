# Helios MCP - Quick Start Guide

## What Was Built

### Original Vision (from PRD)
- **Goal**: Transform stateless AI into evolving personalities with persistent memory
- **Core**: Mathematical inheritance model where specialized personas inherit from base identity
- **Formula**: `inheritance_weight = base_importance / (specialization_level²)`

### What We Actually Have
✅ **7 MCP Tools** working and accessible:
- `get_base_config` - Load base behavioral configuration
- `get_active_persona` - Get specific persona settings
- `merge_behaviors` - Apply inheritance formula
- `list_personas` - Show available personas
- `update_preference` - Modify configurations
- `search_patterns` - Find learned patterns
- `commit_changes` - Git persistence

✅ **UV-based installation** - Simple `uvx helios-mcp` command  
✅ **Factory pattern** - Clean architecture, no global state  
✅ **Lifecycle management** - Health checks, graceful shutdown  
✅ **Git persistence** - All changes versioned  
⚠️ **Tests**: 72% passing (36/50) - needs fixing  

## Installation & Setup

### 1. Install Helios (if published to PyPI)
```bash
# If published:
uvx helios-mcp

# Or from local build:
uv tool install --from dist/helios_mcp-0.1.0-py3-none-any.whl helios-mcp --force
```

### 2. Verify Installation
```bash
helios-mcp --version
# Should output: helios-mcp, version 0.1.0
```

## Testing the MCP Server

### Terminal 1: Start the Server
```bash
# Basic start
helios-mcp --verbose

# Custom config directory
helios-mcp --helios-dir ~/test-helios --verbose

# With health monitoring (production)
helios-mcp --health-check-interval 60
```

### Terminal 2: Test with MCP Inspector
```bash
# Install MCP inspector if needed
npm install -g @modelcontextprotocol/inspector

# Connect to running server
npx @modelcontextprotocol/inspector npx helios-mcp
```

## Interactive Testing

### Test the Core Tools

1. **Check Base Configuration**
```javascript
// In MCP Inspector
await use_mcp_tool("get_base_config", {})
// Should return base configuration with base_importance
```

2. **List Available Personas**
```javascript
await use_mcp_tool("list_personas", {})
// Should list: coder, developer, researcher
```

3. **Test Inheritance Calculation**
```javascript
await use_mcp_tool("merge_behaviors", {
  persona_name: "coder"
})
// Should show:
// - base_importance: 0.7
// - specialization_level: 2
// - inheritance_weight: 0.175 (17.5% base, 82.5% persona)
```

4. **Update a Preference**
```javascript
await use_mcp_tool("update_preference", {
  domain: "coding",
  key: "preferred_language",
  value: "Python"
})
```

5. **Commit Changes**
```javascript
await use_mcp_tool("commit_changes", {
  message: "test: Updated coding preferences"
})
```

## Claude Desktop Integration

Add to Claude Desktop settings:
```json
{
  "mcpServers": {
    "helios": {
      "command": "helios-mcp",
      "args": ["--helios-dir", "~/.helios"]
    }
  }
}
```

Then restart Claude Desktop and look for "helios" in the MCP tools list.

## Quick Functionality Check

### Create Test Configurations
```bash
# Create base identity
cat > ~/.helios/base/identity.yaml << 'EOF'
base_importance: 0.7
behaviors:
  communication_style: "Direct and technical"
  problem_solving: "First principles"
  learning_preference: "Examples first"
EOF

# Create a test persona
cat > ~/.helios/personas/tester.yaml << 'EOF'
specialization_level: 2
behaviors:
  communication_style: "Detailed with examples"
  testing_approach: "Comprehensive coverage"
  preferred_tools: ["pytest", "unittest"]
EOF
```

### Verify Inheritance Math
```bash
# Start server
helios-mcp --verbose

# In another terminal, use the Python test
python -c "
from helios_mcp.inheritance import InheritanceConfig, InheritanceCalculator
config = InheritanceConfig(base_importance=0.7, specialization_level=2)
calc = InheritanceCalculator(config)
weight = calc.calculate_weight()
print(f'Inheritance: {weight:.3f} (Expected: 0.175)')
"
```

## Known Issues to Fix

1. **Test Failures (14/50 failing)**
   - Inheritance bounds clamping issue
   - Tool function test mock issues  
   - Git status assertions

2. **To Debug**
   ```bash
   # Run specific failing test
   uv run pytest tests/test_server.py::TestInheritanceCalculations -xvs
   ```

## What's Working vs What's Not

### ✅ Working
- CLI entry point (`helios-mcp --help`)
- Server starts and runs
- Configuration loading
- Basic inheritance calculation
- Git repository initialization

### ⚠️ Needs Testing
- Full tool integration with Claude Desktop
- Multi-persona switching
- Pattern learning (not implemented)
- Lifecycle recovery from failures

### ❌ Not Implemented Yet
- Learning engine (Phase 2)
- Self-improvement proposals (Phase 3)
- Transient behaviors (Phase 3)
- Obsidian integration (Phase 4)

## Development Testing

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=helios_mcp

# Test specific module
uv run pytest tests/test_cli.py -v

# Run integration test
uv run python tests/test_all_tools.py
```

## Expected Behavior

When everything works correctly:

1. **Server starts** without errors
2. **Tools respond** within 10ms
3. **Inheritance formula** calculates correctly (0.7/4 = 0.175)
4. **Git commits** persist configuration changes
5. **Personas merge** with proper weighting

## Quick Debugging

```bash
# Check if server is running
ps aux | grep helios-mcp

# Check configuration directory
ls -la ~/.helios/

# Check git status
cd ~/.helios && git status

# View server logs (if using systemd or similar)
journalctl -f | grep helios
```

## Feedback Needed

Please test and report:
1. Does the server start cleanly?
2. Do all 7 tools respond in Claude Desktop?
3. Is the inheritance calculation correct?
4. Does git persistence work?
5. Any errors in verbose mode?

---

**Note**: This is a Phase 1 implementation. The core inheritance model works, but learning, evolution, and advanced features are not yet implemented per the original PLAN.md roadmap.