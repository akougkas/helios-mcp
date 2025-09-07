#!/usr/bin/env python3
"""Test script for Helios MCP 5 essential tools."""

import asyncio
import json
from pathlib import Path
from src.helios_mcp.server import (
    get_base_config,
    get_active_persona,
    merge_behaviors,
    update_preference,
    search_patterns,
    commit_changes,
    config,
    loader
)


async def test_essential_tools():
    """Test all 5 essential tools."""
    print("🌞 Testing Helios MCP Essential Tools")
    print("=" * 40)
    
    # Ensure directories exist
    config.ensure_directories()
    
    # Test 1: get_base_config
    print("\n1. Testing get_base_config()...")
    base_result = await get_base_config()
    print(f"   Status: {base_result['status']}")
    if base_result['status'] == 'success':
        print(f"   Base importance: {base_result['config'].get('base_importance', 'not found')}")
        print(f"   Config path: {base_result['path']}")
    
    # Test 2: get_active_persona
    print("\n2. Testing get_active_persona('developer')...")
    persona_result = await get_active_persona("developer")
    print(f"   Status: {persona_result['status']}")
    if persona_result.get('persona'):
        spec_level = persona_result['persona'].get('specialization_level', 'not found')
        print(f"   Specialization level: {spec_level}")
    
    # Test 3: merge_behaviors
    print("\n3. Testing merge_behaviors('developer')...")
    merge_result = await merge_behaviors("developer")
    print(f"   Status: {merge_result['status']}")
    if merge_result['status'] == 'success':
        calc = merge_result['calculation']
        print(f"   Inheritance weight: {calc['inheritance_weight']:.3f}")
        print(f"   Persona weight: {calc['persona_weight']:.3f}")
    
    # Test 4: update_preference
    print("\n4. Testing update_preference('technical', 'test_key', 'test_value')...")
    update_result = await update_preference("technical", "test_key", "test_value")
    print(f"   Status: {update_result['status']}")
    if update_result['status'] == 'success':
        updated = update_result['updated']
        print(f"   Updated: {updated['domain']}.{updated['key']} = {updated['value']}")
    
    # Test 5: search_patterns
    print("\n5. Testing search_patterns('python')...")
    search_result = await search_patterns("python")
    print(f"   Status: {search_result['status']}")
    print(f"   Patterns found: {search_result.get('total_found', 0)}")
    
    # Test 6: commit_changes (commented out to avoid creating git commits during testing)
    print("\n6. Testing commit_changes (dry run)...")
    print("   Skipping actual git commit for testing")
    # commit_result = await commit_changes("Test commit from tool verification")
    # print(f"   Status: {commit_result['status']}")
    
    print("\n" + "=" * 40)
    print("✅ Essential tools test completed!")
    
    # Display summary
    print("\n📊 Configuration Summary:")
    print(f"   Base config path: {config.base_path}")
    print(f"   Personas path: {config.personas_path}")
    print(f"   Learned path: {config.learned_path}")
    print(f"   Temporary path: {config.temporary_path}")
    
    # List available personas
    personas = await loader.list_personas()
    print(f"   Available personas: {len(personas)} found")
    for persona in personas:
        print(f"     - {persona}")


if __name__ == "__main__":
    asyncio.run(test_essential_tools())
