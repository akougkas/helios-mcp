#!/usr/bin/env python3
"""Quick test to validate server imports and initialization."""

import asyncio
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_imports():
    """Test that all imports work correctly."""
    try:
        # Test config imports
        from helios_mcp.config import HeliosConfig, ConfigLoader
        print("✓ Config imports successful")
        
        # Test server imports
        from helios_mcp.server import mcp, get_base_config, get_active_persona, merge_behaviors, commit_changes
        print("✓ Server imports successful")
        
        # Test configuration setup
        config = HeliosConfig.default()
        print(f"✓ Configuration paths set up at: {config.base_path.parent}")
        
        # Test that tools are registered
        tools = mcp.list_tools()
        print(f"✓ FastMCP server initialized with {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description[:50]}...")
        
        # Test a basic tool call
        result = await get_base_config()
        print(f"✓ Base config tool test: {result['status']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_imports())
    if success:
        print("\n🎉 All tests passed! Server is ready to run with: uv run python -m helios_mcp.server")
    else:
        print("\n❌ Tests failed - check errors above")
        sys.exit(1)
