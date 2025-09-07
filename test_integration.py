#!/usr/bin/env python
"""Test Helios MCP integration - verify all components work together."""

import asyncio
import json
from pathlib import Path
from helios_mcp.server import mcp


async def test_integration():
    """Run integration tests for Helios MCP."""
    print("🌞 Testing Helios MCP Integration\n")
    
    # Get the actual functions from the decorated tools
    tools = mcp._tools
    get_base_config = tools["get_base_config"].func
    get_active_persona = tools["get_active_persona"].func
    merge_behaviors = tools["merge_behaviors"].func
    commit_changes = tools["commit_changes"].func
    list_personas = tools["list_personas"].func
    
    # Test 1: Get base configuration
    print("1. Testing get_base_config()...")
    base = await get_base_config()
    assert base["status"] == "success", "Failed to load base config"
    assert "base_importance" in base["config"], "Missing base_importance"
    print(f"   ✅ Base config loaded with base_importance: {base['config']['base_importance']}")
    
    # Test 2: List personas
    print("\n2. Testing list_personas()...")
    personas = await list_personas()
    assert personas["status"] == "success", "Failed to list personas"
    assert len(personas["personas"]) > 0, "No personas found"
    print(f"   ✅ Found {len(personas['personas'])} personas: {', '.join(personas['personas'])}")
    
    # Test 3: Get active persona
    print("\n3. Testing get_active_persona()...")
    persona_name = personas["personas"][0]  # Use first persona
    persona = await get_active_persona(persona_name=persona_name)
    assert persona["status"] == "success", f"Failed to load persona {persona_name}"
    assert "specialization_level" in persona["persona"], "Missing specialization_level"
    print(f"   ✅ Loaded persona '{persona_name}' with specialization_level: {persona['persona']['specialization_level']}")
    
    # Test 4: Merge behaviors (THE CORE!)
    print("\n4. Testing merge_behaviors() - Core inheritance calculation...")
    merged = await merge_behaviors(persona_name=persona_name)
    assert merged["status"] == "success", "Failed to merge behaviors"
    assert "calculation" in merged, "Missing inheritance calculation"
    calc = merged["calculation"]
    print(f"   ✅ Inheritance calculation:")
    print(f"      - base_importance: {calc['base_importance']}")
    print(f"      - specialization_level: {calc['specialization_level']}")
    print(f"      - inheritance_weight: {calc['inheritance_weight']:.3f}")
    print(f"      - persona_weight: {calc['persona_weight']:.3f}")
    
    # Verify the formula
    expected_weight = calc['base_importance'] / (calc['specialization_level'] ** 2)
    assert abs(calc['inheritance_weight'] - expected_weight) < 0.001, "Inheritance formula incorrect!"
    print(f"   ✅ Formula verified: {calc['base_importance']} / {calc['specialization_level']}² = {expected_weight:.3f}")
    
    # Test 5: Git persistence
    print("\n5. Testing commit_changes()...")
    commit = await commit_changes(message="test: Integration test commit")
    assert commit["status"] in ["success", "info"], "Failed to commit changes"
    if commit["status"] == "success":
        print(f"   ✅ Changes committed with hash: {commit['commit']['commit_hash']}")
    else:
        print(f"   ℹ️  No changes to commit")
    
    print("\n" + "="*50)
    print("✨ ALL TESTS PASSED! Helios MCP is working correctly.")
    print("="*50)
    
    # Display merged behavior sample
    print("\n📋 Sample merged behavior:")
    if "behaviors" in merged["merged_behaviors"]:
        behaviors = merged["merged_behaviors"]["behaviors"]
        for key, value in list(behaviors.items())[:3]:
            print(f"   - {key}: {value}")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_integration())
    exit(0 if success else 1)