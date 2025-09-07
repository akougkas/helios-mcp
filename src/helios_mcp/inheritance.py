"""Inheritance calculation module for Helios MCP.

Provides weighted behavior inheritance between base configurations and specialized personas.
This is the heart of Helios - calculating how much of the base behavior to inherit
based on specialization level and base importance.
"""

from __future__ import annotations

from typing import Any, Dict, Union
from pathlib import Path
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class InheritanceConfig:
    """Configuration for inheritance calculations."""
    
    base_importance: float  # How important the base configuration is (0.0-1.0)
    specialization_level: int  # How specialized this persona is (1+ integers)
    min_weight: float = 0.01  # Minimum inheritance weight to prevent complete override
    max_weight: float = 0.99  # Maximum inheritance weight to allow some specialization


class InheritanceCalculator:
    """Calculate inheritance weights for behavior merging.
    
    Implements the core Helios formula:
    inheritance_weight = base_importance / (specialization_level ** 2)
    
    Higher base_importance = stronger inheritance from base
    Higher specialization_level = weaker inheritance, more persona specialization
    """
    
    def __init__(self, config: InheritanceConfig | None = None) -> None:
        """Initialize calculator with inheritance configuration."""
        self.config = config or InheritanceConfig(
            base_importance=0.7,
            specialization_level=2
        )
        
    def calculate_weight(
        self, 
        base_importance: float | None = None,
        specialization_level: int | None = None
    ) -> float:
        """Calculate inheritance weight using the core Helios formula.
        
        Args:
            base_importance: Override default base importance (0.0-1.0)
            specialization_level: Override default specialization level (1+)
            
        Returns:
            Float between min_weight and max_weight representing inheritance strength
            
        Example:
            >>> calc = InheritanceCalculator()
            >>> calc.calculate_weight(base_importance=0.7, specialization_level=2)
            0.175
        """
        importance = base_importance or self.config.base_importance
        level = specialization_level or self.config.specialization_level
        
        # Validate inputs
        if not 0.0 <= importance <= 1.0:
            raise ValueError(f"base_importance must be between 0.0 and 1.0, got {importance}")
        if level < 1:
            raise ValueError(f"specialization_level must be >= 1, got {level}")
            
        # Core Helios inheritance formula
        raw_weight = importance / (level ** 2)
        
        # Clamp to configured bounds
        weight = max(self.config.min_weight, min(self.config.max_weight, raw_weight))
        
        logger.debug(
            f"Calculated inheritance weight: {weight:.3f} "
            f"(base_importance={importance}, specialization_level={level})"
        )
        
        return weight


class BehaviorMerger:
    """Merge base and persona behaviors using weighted inheritance.
    
    Handles deep merging of nested dictionaries, applying inheritance weights
    at each level to blend base and specialized behaviors appropriately.
    """
    
    def __init__(self, calculator: InheritanceCalculator | None = None) -> None:
        """Initialize merger with inheritance calculator."""
        self.calculator = calculator or InheritanceCalculator()
        
    def merge_behaviors(
        self,
        base_config: Dict[str, Any],
        persona_config: Dict[str, Any],
        inheritance_weight: float | None = None,
        base_importance: float | None = None,
        specialization_level: int | None = None
    ) -> Dict[str, Any]:
        """Merge base and persona configurations using weighted inheritance.
        
        Args:
            base_config: Base behavioral configuration
            persona_config: Specialized persona configuration
            inheritance_weight: Pre-calculated weight (overrides calculation)
            base_importance: Base importance for weight calculation
            specialization_level: Specialization level for weight calculation
            
        Returns:
            Merged configuration with weighted inheritance applied
        """
        if inheritance_weight is None:
            inheritance_weight = self.calculator.calculate_weight(
                base_importance=base_importance,
                specialization_level=specialization_level
            )
            
        logger.info(
            f"Merging behaviors with inheritance weight: {inheritance_weight:.3f}"
        )
        
        return self._deep_merge(
            base_config, 
            persona_config, 
            inheritance_weight
        )
        
    def _deep_merge(
        self, 
        base: Dict[str, Any], 
        persona: Dict[str, Any], 
        weight: float
    ) -> Dict[str, Any]:
        """Recursively merge nested dictionaries with inheritance weighting.
        
        Args:
            base: Base configuration dictionary
            persona: Persona configuration dictionary  
            weight: Inheritance weight (higher = more base influence)
            
        Returns:
            Deep-merged configuration dictionary
        """
        result: Dict[str, Any] = {}
        
        # Get all unique keys from both configurations
        all_keys = set(base.keys()) | set(persona.keys())
        
        for key in all_keys:
            base_value = base.get(key)
            persona_value = persona.get(key)
            
            if base_value is None:
                # Only in persona - use persona value
                result[key] = persona_value
            elif persona_value is None:
                # Only in base - use base value
                result[key] = base_value
            else:
                # In both - need to merge based on types
                result[key] = self._merge_values(
                    base_value, persona_value, weight, key
                )
                
        return result
        
    def _merge_values(
        self, 
        base_value: Any, 
        persona_value: Any, 
        weight: float,
        key: str
    ) -> Any:
        """Merge two values based on their types and inheritance weight.
        
        Args:
            base_value: Value from base configuration
            persona_value: Value from persona configuration
            weight: Inheritance weight
            key: Configuration key for logging
            
        Returns:
            Merged value
        """
        # Both are dictionaries - recursive merge
        if isinstance(base_value, dict) and isinstance(persona_value, dict):
            logger.debug(f"Deep merging nested dict for key: {key}")
            return self._deep_merge(base_value, persona_value, weight)
            
        # Both are lists - merge based on weight
        elif isinstance(base_value, list) and isinstance(persona_value, list):
            return self._merge_lists(base_value, persona_value, weight)
            
        # Both are numeric - weighted average
        elif isinstance(base_value, (int, float)) and isinstance(persona_value, (int, float)):
            merged = base_value * weight + persona_value * (1 - weight)
            logger.debug(f"Numeric merge for {key}: {base_value} * {weight:.3f} + {persona_value} * {1-weight:.3f} = {merged}")
            return type(base_value)(merged) if isinstance(base_value, int) else merged
            
        # Both are strings - choose based on weight (threshold at 0.5)
        elif isinstance(base_value, str) and isinstance(persona_value, str):
            chosen = base_value if weight > 0.5 else persona_value
            logger.debug(f"String choice for {key}: chose {'base' if weight > 0.5 else 'persona'} ({chosen})")
            return chosen
            
        # Both are booleans - choose based on weight
        elif isinstance(base_value, bool) and isinstance(persona_value, bool):
            chosen = base_value if weight > 0.5 else persona_value
            logger.debug(f"Boolean choice for {key}: chose {'base' if weight > 0.5 else 'persona'} ({chosen})")
            return chosen
            
        # Different types - persona wins (specialization takes precedence)
        else:
            logger.debug(f"Type mismatch for {key}: using persona value ({type(persona_value).__name__})")
            return persona_value
            
    def _merge_lists(
        self, 
        base_list: list[Any], 
        persona_list: list[Any], 
        weight: float
    ) -> list[Any]:
        """Merge two lists based on inheritance weight.
        
        Strategy:
        - High weight (>0.7): Base list with persona items appended
        - Medium weight (0.3-0.7): Interleaved based on weight ratio  
        - Low weight (<0.3): Persona list with base items appended
        
        Args:
            base_list: List from base configuration
            persona_list: List from persona configuration
            weight: Inheritance weight
            
        Returns:
            Merged list
        """
        if weight > 0.7:
            # Strong base inheritance - base first, persona appends
            result = base_list.copy()
            result.extend(item for item in persona_list if item not in result)
            logger.debug(f"List merge: base-dominant (weight={weight:.3f})")
        elif weight < 0.3:
            # Strong persona specialization - persona first, base appends
            result = persona_list.copy()
            result.extend(item for item in base_list if item not in result)
            logger.debug(f"List merge: persona-dominant (weight={weight:.3f})")
        else:
            # Balanced merge - interleave based on weight ratio
            base_ratio = int(len(base_list) * weight)
            persona_ratio = int(len(persona_list) * (1 - weight))
            
            result = []
            b_idx = p_idx = 0
            
            # Interleave items based on ratio
            while b_idx < len(base_list) or p_idx < len(persona_list):
                # Add base items
                for _ in range(min(base_ratio, len(base_list) - b_idx)):
                    if b_idx < len(base_list):
                        result.append(base_list[b_idx])
                        b_idx += 1
                        
                # Add persona items
                for _ in range(min(persona_ratio, len(persona_list) - p_idx)):
                    if p_idx < len(persona_list):
                        result.append(persona_list[p_idx])
                        p_idx += 1
                        
            logger.debug(f"List merge: balanced interleave (weight={weight:.3f})")
            
        return result


def create_inheritance_calculator(
    base_importance: float = 0.7,
    specialization_level: int = 2,
    min_weight: float = 0.01,
    max_weight: float = 0.99
) -> InheritanceCalculator:
    """Factory function to create inheritance calculator with custom config.
    
    Args:
        base_importance: How important base configuration is (0.0-1.0)
        specialization_level: How specialized the persona is (1+)
        min_weight: Minimum inheritance weight
        max_weight: Maximum inheritance weight
        
    Returns:
        Configured InheritanceCalculator instance
    """
    config = InheritanceConfig(
        base_importance=base_importance,
        specialization_level=specialization_level,
        min_weight=min_weight,
        max_weight=max_weight
    )
    return InheritanceCalculator(config)


def create_behavior_merger(
    base_importance: float = 0.7,
    specialization_level: int = 2
) -> BehaviorMerger:
    """Factory function to create behavior merger with custom inheritance config.
    
    Args:
        base_importance: How important base configuration is (0.0-1.0) 
        specialization_level: How specialized the persona is (1+)
        
    Returns:
        Configured BehaviorMerger instance
    """
    calculator = create_inheritance_calculator(
        base_importance=base_importance,
        specialization_level=specialization_level
    )
    return BehaviorMerger(calculator)
