#!/usr/bin/env python
"""Quick test of Helios MCP functionality."""

import asyncio
import sys
from pathlib import Path

# Import the server module to get the mcp instance
from helios_mcp import server


async def quick_test():
    """Quick test of core functionality."""
    print("🌞 Quick Helios MCP Test\n")
    
    # Test 1: Check tools are registered
    print("1. Checking registered tools...")
    tools = await server.mcp.get_tools()
    
    # Handle different return types from get_tools()
    if isinstance(tools, dict):
        tool_names = list(tools.keys())
    elif isinstance(tools, list):
        tool_names = [str(tool) for tool in tools]
    else:
        tool_names = []
    
    print(f"   ✅ Found {len(tool_names)} tools: {', '.join(tool_names)}")
    
    # Test 2: Check configuration exists
    print("\n2. Checking configuration...")
    config_path = Path.home() / ".helios"
    if config_path.exists():
        print(f"   ✅ Configuration directory exists at {config_path}")
        
        # Check for base config
        base_config = config_path / "base" / "identity.yaml"
        if base_config.exists():
            print(f"   ✅ Base configuration found")
        
        # Check for personas
        personas_dir = config_path / "personas"
        if personas_dir.exists():
            personas = list(personas_dir.glob("*.yaml"))
            print(f"   ✅ Found {len(personas)} personas")
            for p in personas:
                print(f"      - {p.stem}")
    
    # Test 3: Check imports work
    print("\n3. Testing imports...")
    try:
        from helios_mcp.inheritance import InheritanceCalculator, BehaviorMerger, InheritanceConfig
        from helios_mcp.git_store import GitStore
        from helios_mcp.config import ConfigLoader
        print("   ✅ All core modules import successfully")
        
        # Test inheritance calculation
        config = InheritanceConfig(base_importance=0.7, specialization_level=2)
        calc = InheritanceCalculator(config)
        weight = calc.calculate_weight()
        print(f"   ✅ Inheritance calculation: 0.7 / 2² = {weight:.3f}")
        
        # Verify formula
        expected = 0.7 / (2 ** 2)
        assert abs(weight - expected) < 0.001, "Formula incorrect!"
        print(f"   ✅ Formula verified: {expected:.3f}")
        
    except Exception as e:
        print(f"   ❌ Import error: {e}")
        return False
    
    print("\n" + "="*50)
    print("✨ QUICK TEST PASSED! Core components are working.")
    print("="*50)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(quick_test())
    sys.exit(0 if success else 1)