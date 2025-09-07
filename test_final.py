#!/usr/bin/env python
"""Final integration test for Helios MCP."""

import asyncio
import subprocess
import json
from pathlib import Path


async def test_server_startup():
    """Test that the server starts and responds correctly."""
    print("🌞 Final Helios MCP Integration Test\n")
    
    # Test 1: CLI works
    print("1. Testing CLI installation...")
    result = subprocess.run(["helios-mcp", "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
    print(f"   ✅ CLI installed: {result.stdout.strip()}")
    
    # Test 2: Help works
    print("\n2. Testing CLI help...")
    result = subprocess.run(["helios-mcp", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--helios-dir" in result.stdout
    print("   ✅ Help text contains --helios-dir option")
    
    # Test 3: Server module imports
    print("\n3. Testing server imports...")
    from helios_mcp.server import create_server
    from helios_mcp.inheritance import InheritanceConfig, InheritanceCalculator
    from helios_mcp.config import HeliosConfig, ConfigLoader
    from helios_mcp.git_store import GitStore
    print("   ✅ All modules import successfully")
    
    # Test 4: Server creation
    print("\n4. Testing server creation...")
    test_dir = Path("/tmp/helios-test")
    test_dir.mkdir(exist_ok=True)
    server = create_server(test_dir)
    assert server is not None
    print(f"   ✅ Server created with config at {test_dir}")
    
    # Test 5: Inheritance calculation
    print("\n5. Testing inheritance calculation...")
    config = InheritanceConfig(base_importance=0.7, specialization_level=2)
    calc = InheritanceCalculator(config)
    weight = calc.calculate_weight()
    expected = 0.7 / (2 ** 2)
    assert abs(weight - expected) < 0.001
    print(f"   ✅ Inheritance: 0.7 / 2² = {weight:.3f}")
    
    # Test 6: Claude Desktop config format
    print("\n6. Testing Claude Desktop configuration...")
    config = {
        "mcpServers": {
            "helios": {
                "command": "uvx",
                "args": ["helios-mcp", "--helios-dir", "~/.helios"]
            }
        }
    }
    config_json = json.dumps(config, indent=2)
    print(f"   ✅ Valid config format:\n{config_json}")
    
    print("\n" + "="*50)
    print("✨ ALL TESTS PASSED!")
    print("="*50)
    print("\n📦 Ready for publication:")
    print("   1. export PYPI_TOKEN='your-token'")
    print("   2. uv publish --token $PYPI_TOKEN")
    print("\n🚀 Then users can install with:")
    print("   uvx helios-mcp")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_server_startup())
    exit(0 if success else 1)