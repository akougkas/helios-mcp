#!/usr/bin/env python
"""Example demonstrating the gravitational dynamics of Helios learning system.

This example shows how learning doesn't replace but adds mass to the system,
shifting the dynamics through weighted inheritance.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from helios_mcp.server import create_server
from helios_mcp.learning import LearnBehaviorParams, TuneWeightParams, EvolveBehaviorParams
from helios_mcp.inheritance import InheritanceCalculator


async def demonstrate_gravitational_dynamics():
    """Demonstrate how learning shifts the gravitational dynamics."""
    
    print("=" * 60)
    print("HELIOS LEARNING SYSTEM - GRAVITATIONAL DYNAMICS DEMO")
    print("=" * 60)
    
    # Create a test directory
    test_dir = Path("/tmp/helios_demo")
    test_dir.mkdir(exist_ok=True)
    
    # Initialize server
    server = create_server(test_dir)
    print(f"\n✨ Helios server initialized at {test_dir}")
    
    # Create base configuration
    base_dir = test_dir / "base"
    base_dir.mkdir(exist_ok=True)
    base_config = base_dir / "identity.yaml"
    base_config.write_text("""base_importance: 0.7
behaviors:
  communication_style: "Direct and technical"
  problem_solving: "First principles thinking"
  tools:
    - "vim"
    - "git"
""")
    print("\n📋 Base configuration created:")
    print("   - base_importance: 0.7")
    print("   - Core behaviors defined")
    
    # Create developer persona
    personas_dir = test_dir / "personas"
    personas_dir.mkdir(exist_ok=True)
    dev_persona = personas_dir / "developer.yaml"
    dev_persona.write_text("""specialization_level: 2
behaviors:
  communication_style: "Code-focused with examples"
  preferred_language: "Python"
  tools:
    - "pytest"
    - "pip"
""")
    print("\n🎭 Developer persona created:")
    print("   - specialization_level: 2")
    print("   - Initial tools: [pytest, pip]")
    
    # Calculate initial inheritance
    calculator = InheritanceCalculator()
    initial_weight = calculator.calculate_weight(
        base_importance=0.7,
        specialization_level=2
    )
    print(f"\n⚖️  Initial inheritance weight: {initial_weight:.1%} base influence")
    print(f"   (Persona has {(1-initial_weight):.1%} influence)")
    
    # Initialize git
    import subprocess
    subprocess.run(["git", "init"], cwd=test_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "helios@demo"], cwd=test_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Helios Demo"], cwd=test_dir, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=test_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial configuration"], cwd=test_dir, capture_output=True)
    
    print("\n" + "=" * 60)
    print("DEMONSTRATION: Learning adds mass, doesn't erase")
    print("=" * 60)
    
    # Learning example 1: Add a new tool preference
    from helios_mcp.learning import LearningManager
    learning_manager = LearningManager(test_dir)
    
    print("\n🌟 LEARNING EVENT 1: Developer learns to use 'uv' instead of pip")
    params = LearnBehaviorParams(
        persona="developer",
        key="behaviors.package_manager",
        value="uv"
    )
    result = await learning_manager.learn_behavior(params)
    print(f"   Result: {result['message']}")
    print(f"   Note: 'pip' still exists in tools list - we added, not replaced!")
    
    # Show the persona still has pip
    with open(dev_persona) as f:
        content = f.read()
        if "pip" in content:
            print("   ✅ Confirmed: 'pip' still in configuration")
    
    print("\n🌟 LEARNING EVENT 2: Tune specialization level")
    print("   Current specialization: 2 (17.5% base influence)")
    tune_params = TuneWeightParams(
        target="developer",
        parameter="specialization_level",
        value=3.0
    )
    result = await learning_manager.tune_weight(tune_params)
    
    new_weight = calculator.calculate_weight(
        base_importance=0.7,
        specialization_level=3.0
    )
    print(f"   New specialization: 3 ({new_weight:.1%} base influence)")
    print(f"   🔄 Gravitational shift: Base influence decreased by {(initial_weight - new_weight):.1%}")
    print("   Interpretation: Developer persona became more specialized, less influenced by base")
    
    print("\n🌟 LEARNING EVENT 3: Evolve behavior to base")
    print("   'package_manager: uv' is so good, let's promote it to base!")
    evolve_params = EvolveBehaviorParams(
        from_config="developer",
        to_config="base",
        key="behaviors.package_manager"
    )
    result = await learning_manager.evolve_behavior(evolve_params)
    print(f"   Result: {result['message']}")
    print("   🌍 Now ALL personas will inherit the 'uv' preference from base!")
    
    # Verify it's in base
    with open(base_config) as f:
        if "package_manager" in f.read():
            print("   ✅ Confirmed: package_manager now in base configuration")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHTS: The Gravitational Model")
    print("=" * 60)
    
    print("""
1. **Learning is Additive**: When we learned 'uv', we didn't delete 'pip'.
   The system gained mass, not replaced mass.

2. **Weights Shift Dynamics**: Increasing specialization_level from 2→3
   reduced base influence from 17.5% to 7.8%. The persona became more
   independent, like a planet moving to a wider orbit.

3. **Evolution Changes Systems**: Moving 'package_manager' from persona
   to base affects the entire system. Now all personas inherit this
   preference - a system-wide gravitational shift.

4. **Git Tracks Everything**: Every learning event is a commit. We can
   revert any change, returning to previous gravitational states.

This is the power of Helios: behaviors accumulate and interact through
mathematical inheritance, creating evolving AI personalities that grow
richer over time without losing their history.
""")
    
    # Show git log
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=test_dir,
        capture_output=True,
        text=True
    )
    print("📜 Git History (showing gravitational evolution):")
    for line in result.stdout.strip().split('\n'):
        print(f"   {line}")
    
    print("\n✨ Demo complete! The ~/.helios directory works the same way.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demonstrate_gravitational_dynamics())