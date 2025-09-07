# FastMCP Testing Patterns
**Updated**: 2025-09-07
**Version**: FastMCP 2.2.6+
**Source**: Official docs, GitHub issues, jlowin.dev

## Quick Reference
In-memory testing with pytest fixtures and FastMCP Client:
```python
async with Client(mcp_server) as client:
    result = await client.call_tool("tool_name", {"param": "value"})
```

## Core Testing Pattern

### 1. Pytest Fixture Setup
```python
import pytest
from fastmcp import FastMCP, Client

@pytest.fixture
def mcp_server():
    """Create test MCP server with decorated tools"""
    server = FastMCP("TestServer")
    
    @server.tool
    def get_base_config() -> dict:
        """Get base configuration"""
        return {"base_importance": 0.8, "version": "1.0"}
    
    @server.tool
    def calculate_weight(specialization_level: int, base_importance: float = 0.8) -> float:
        """Calculate inheritance weight"""
        if specialization_level <= 0:
            raise ValueError("Specialization level must be positive")
        return base_importance / (specialization_level ** 2)
    
    return server
```

### 2. Basic Tool Testing
```python
async def test_get_base_config(mcp_server):
    """Test base configuration retrieval"""
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_base_config", {})
        # Result format: result.content[0].text for newer versions
        # or result[0].text for older versions
        config = json.loads(result[0].text)
        assert config["base_importance"] == 0.8
        assert "version" in config
```

### 3. Parameterized Tool Testing
```python
async def test_calculate_weight_with_params(mcp_server):
    """Test weight calculation with various parameters"""
    async with Client(mcp_server) as client:
        # Test with explicit parameters
        result = await client.call_tool("calculate_weight", {
            "specialization_level": 2,
            "base_importance": 0.9
        })
        weight = float(result[0].text)
        assert weight == 0.225  # 0.9 / (2**2)
        
        # Test with default parameter
        result = await client.call_tool("calculate_weight", {
            "specialization_level": 1
        })
        weight = float(result[0].text)
        assert weight == 0.8  # 0.8 / (1**2)
```

### 4. Error Handling Testing
```python
async def test_calculate_weight_error_handling(mcp_server):
    """Test tool error conditions"""
    async with Client(mcp_server) as client:
        with pytest.raises(Exception):  # Specific exception type may vary
            await client.call_tool("calculate_weight", {
                "specialization_level": 0
            })
```

## Advanced Testing Patterns

### Async Tool Testing
```python
@pytest.fixture
def async_mcp_server():
    server = FastMCP("AsyncServer")
    
    @server.tool
    async def async_process(data: str) -> str:
        """Async tool for testing"""
        await asyncio.sleep(0.1)  # Simulate async work
        return f"Processed: {data}"
    
    return server

async def test_async_tool(async_mcp_server):
    async with Client(async_mcp_server) as client:
        result = await client.call_tool("async_process", {"data": "test"})
        assert result[0].text == "Processed: test"
```

### Complex Data Testing
```python
async def test_complex_data_handling(mcp_server):
    """Test tools that return complex data structures"""
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_base_config", {})
        config = json.loads(result[0].text)
        
        # Validate structure
        assert isinstance(config, dict)
        assert "base_importance" in config
        assert isinstance(config["base_importance"], float)
        assert 0.0 <= config["base_importance"] <= 1.0
```

## Testing Best Practices

### 1. In-Memory Testing Benefits
- **No subprocess management**: Direct server instantiation
- **Fast execution**: No network overhead
- **Real protocol**: Uses actual MCP transport internally
- **Deterministic**: No external dependencies

### 2. Key Principles
- Test smallest units of behavior
- Focus on assertable outcomes
- Document server contracts through tests
- Create safety net for refactoring

### 3. Fixture Guidelines
```python
# ✅ GOOD: Simple fixture, client in test
@pytest.fixture
def mcp_server():
    return FastMCP("TestServer")

async def test_tool(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("tool_name", {})

# ❌ AVOID: Async fixtures with event loop issues
```

### 4. Result Format Compatibility
```python
# Handle version differences
try:
    # Newer FastMCP versions
    text_result = result.content[0].text
except AttributeError:
    # Older FastMCP versions
    text_result = result[0].text
```

## Common Testing Issues

### Issue: Event Loop Conflicts
**Solution**: Avoid async fixtures that span different event loops. Instantiate clients directly within test functions.

### Issue: Result Format Changes
**Solution**: Check FastMCP version or handle both `result[0].text` and `result.content[0].text` formats.

### Issue: Parameter Validation
**Solution**: Test both valid parameters and error conditions explicitly.

## Testing Tools vs Direct Function Access

### MCP Tool Testing (Recommended)
```python
# Tests the full MCP protocol flow
async with Client(mcp_server) as client:
    result = await client.call_tool("get_base_config", {})
```

### Direct Function Testing (For Internal Logic)
```python
# For testing internal logic without MCP overhead
def test_direct_function():
    # Access the underlying function if needed
    # Note: This bypasses MCP protocol validation
    from your_module import get_base_config
    result = get_base_config()
    assert result["base_importance"] == 0.8
```

### When to Use Each
- **MCP Tool Testing**: Test complete protocol flow, parameter validation, serialization
- **Direct Function Testing**: Test pure business logic, complex calculations, edge cases

## Example Test Suite Structure
```
tests/
├── conftest.py           # Shared fixtures
├── test_tools.py         # Tool functionality tests
├── test_inheritance.py   # Inheritance calculation tests
├── test_error_handling.py # Error condition tests
└── test_integration.py   # End-to-end tests
```

This testing approach ensures your FastMCP tools work correctly at both the protocol level and the business logic level.