"""Inheritance calculation module for Helios MCP.

Provides weighted behavior inheritance between base configurations and specialized personas.
This is the heart of Helios - calculating how much of the base behavior to inherit
based on specialization level and base importance.
"""

from __future__ import annotations

from typing import Any, Dict, Union, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import logging

from .cache import get_cache, cached

logger = logging.getLogger(__name__)


@dataclass
class InheritanceConfig:
    """Configuration for inheritance calculations."""
    
    base_importance: float  # How important the base configuration is (0.0-1.0)
    specialization_level: int  # How specialized this persona is (1+ integers)
    min_weight: float = 0.01  # Minimum inheritance weight to prevent complete override
    max_weight: float = 1.0  # Maximum inheritance weight (1.0 allows full base inheritance)


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
        importance = base_importance if base_importance is not None else self.config.base_importance
        level = specialization_level if specialization_level is not None else self.config.specialization_level
        
        # Validate inputs with improved bounds checking
        if not 0.0 <= importance <= 1.0:
            raise ValueError(f"base_importance must be between 0.0 and 1.0, got {importance}")
        if level < 1:
            raise ValueError(f"specialization_level must be >= 1, got {level}")
        
        # Add upper bound validation to prevent underflow
        if level > 1000:
            logger.warning(f"Extremely high specialization_level {level} may cause underflow, clamping to 1000")
            level = 1000
            
        # Core Helios inheritance formula
        raw_weight = importance / (level ** 2)
        
        # Clamp to configured bounds with better precision handling
        weight = max(self.config.min_weight, min(self.config.max_weight, raw_weight))
        
        # Check for underflow condition and warn
        if raw_weight < self.config.min_weight:
            logger.warning(
                f"Inheritance weight {raw_weight:.6f} below minimum {self.config.min_weight}, "
                f"clamped to minimum (specialization_level={level} may be too high)"
            )
        
        logger.debug(
            f"Calculated inheritance weight: {weight:.6f} "
            f"(raw: {raw_weight:.6f}, base_importance={importance}, specialization_level={level})"
        )
        
        return weight


class BehaviorMerger:
    """Merge base and persona behaviors using weighted inheritance.
    
    Handles deep merging of nested dictionaries, applying inheritance weights
    at each level to blend base and specialized behaviors appropriately.
    
    Features high-performance optimizations:
    - Memoization of merge operations
    - Optimized list merging (O(n) instead of O(n²))
    - Cache invalidation on configuration changes
    """
    
    def __init__(self, calculator: InheritanceCalculator | None = None) -> None:
        """Initialize merger with inheritance calculator."""
        self.calculator = calculator or InheritanceCalculator()
        self.cache = get_cache()
        self._merge_stats = {"cache_hits": 0, "cache_misses": 0, "computations": 0}
        
    def merge_behaviors(
        self,
        base_config: Dict[str, Any],
        persona_config: Dict[str, Any],
        inheritance_weight: float | None = None,
        base_importance: float | None = None,
        specialization_level: int | None = None
    ) -> Dict[str, Any]:
        """Merge base and persona configurations using weighted inheritance with caching.
        
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
        
        # Create cache key from configuration hashes and weight
        cache_key = self._create_merge_cache_key(
            base_config, persona_config, inheritance_weight
        )
        
        # Try cache first
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            self._merge_stats["cache_hits"] += 1
            logger.debug(f"Cache hit for merge operation (weight={inheritance_weight:.3f})")
            return cached_result
        
        self._merge_stats["cache_misses"] += 1
        self._merge_stats["computations"] += 1
        
        logger.info(
            f"Computing merge with inheritance weight: {inheritance_weight:.3f}"
        )
        
        result = self._deep_merge(
            base_config, 
            persona_config, 
            inheritance_weight
        )
        
        # Cache result with inheritance-specific TTL
        self.cache.set(cache_key, result, ttl=self.cache.inheritance_ttl)
        
        return result
        
    def _deep_merge(
        self, 
        base: Dict[str, Any], 
        persona: Dict[str, Any], 
        weight: float
    ) -> Dict[str, Any]:
        """Recursively merge nested dictionaries with inheritance weighting.
        
        Optimized version with reduced memory allocation and faster key processing.
        
        Args:
            base: Base configuration dictionary
            persona: Persona configuration dictionary  
            weight: Inheritance weight (higher = more base influence)
            
        Returns:
            Deep-merged configuration dictionary
        """
        # Pre-allocate result dict with estimated size
        estimated_size = len(base) + len(persona)
        result: Dict[str, Any] = {}
        
        # Process base keys first (most common case)
        for key, base_value in base.items():
            persona_value = persona.get(key)
            if persona_value is None:
                # Only in base - direct assignment
                result[key] = base_value
            else:
                # In both - merge based on types
                result[key] = self._merge_values(
                    base_value, persona_value, weight, key
                )
        
        # Process remaining persona keys (only those not in base)
        for key, persona_value in persona.items():
            if key not in base:
                # Only in persona - direct assignment
                result[key] = persona_value
                
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
            # Use proper rounding for integer types instead of truncation
            if isinstance(base_value, int) and isinstance(persona_value, int):
                return round(merged)
            elif isinstance(base_value, int):
                return round(merged)
            else:
                return merged
            
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
            logger.warning(
                f"Type mismatch for {key}: base_value={type(base_value).__name__}({base_value}), "
                f"persona_value={type(persona_value).__name__}({persona_value}), "
                f"using persona value (specialization takes precedence)"
            )
            return persona_value
            
    def _merge_lists(
        self, 
        base_list: list[Any], 
        persona_list: list[Any], 
        weight: float
    ) -> list[Any]:
        """Optimized list merging with O(n) complexity.
        
        Strategy:
        - High weight (>0.7): Base list with persona items appended
        - Medium weight (0.3-0.7): Interleaved based on weight ratio  
        - Low weight (<0.3): Persona list with base items appended
        
        Uses set-based deduplication for O(n) performance instead of O(n²).
        
        Args:
            base_list: List from base configuration
            persona_list: List from persona configuration
            weight: Inheritance weight
            
        Returns:
            Merged list
        """
        # Fast path for empty lists
        if not base_list:
            return persona_list.copy()
        if not persona_list:
            return base_list.copy()
        
        # Use sets for O(n) deduplication instead of O(n²) "in" checks
        base_set = set(base_list) if len(base_list) > 10 else None
        persona_set = set(persona_list) if len(persona_list) > 10 else None
        
        if weight > 0.7:
            # Strong base inheritance - base first, persona appends
            result = base_list.copy()
            seen = base_set if base_set else set(base_list)
            
            # Add unique persona items
            for item in persona_list:
                if item not in seen:
                    result.append(item)
                    seen.add(item)
            
            logger.debug(
                f"List merge: base-dominant (weight={weight:.3f}, "
                f"final_size={len(result)}, unique_added={len(result) - len(base_list)})"
            )
        elif weight < 0.3:
            # Strong persona specialization - persona first, base appends  
            result = persona_list.copy()
            seen = persona_set if persona_set else set(persona_list)
            
            # Add unique base items
            for item in base_list:
                if item not in seen:
                    result.append(item)
                    seen.add(item)
            
            logger.debug(
                f"List merge: persona-dominant (weight={weight:.3f}, "
                f"final_size={len(result)}, unique_added={len(result) - len(persona_list)})"
            )
        else:
            # Balanced merge with optimized interleaving
            result = self._interleave_lists_optimized(base_list, persona_list, weight)
            
            logger.debug(f"List merge: balanced interleave (weight={weight:.3f}, final_size={len(result)})")
            
        return result

    def _interleave_lists_optimized(
        self, 
        base_list: list[Any], 
        persona_list: list[Any], 
        weight: float
    ) -> list[Any]:
        """Optimized balanced list interleaving with O(n) complexity.
        
        Args:
            base_list: Base list items
            persona_list: Persona list items
            weight: Inheritance weight for ratio calculation
            
        Returns:
            Interleaved list maintaining proper weight ratios
        """
        # Calculate optimal batch sizes for interleaving
        total_items = len(base_list) + len(persona_list)
        base_target = max(1, round(total_items * weight))
        persona_target = max(1, total_items - base_target)
        
        # Calculate step sizes for even distribution
        if base_target >= len(base_list):
            # Use all base items, distribute persona items evenly
            base_step = 1
            persona_step = max(1, len(persona_list) // (base_target - len(base_list) + 1))
        elif persona_target >= len(persona_list):
            # Use all persona items, distribute base items evenly
            persona_step = 1
            base_step = max(1, len(base_list) // (persona_target - len(persona_list) + 1))
        else:
            # Calculate balanced steps
            base_step = max(1, len(base_list) // base_target)
            persona_step = max(1, len(persona_list) // persona_target)
        
        result = []
        b_idx = p_idx = 0
        
        # Interleave with calculated steps
        while b_idx < len(base_list) or p_idx < len(persona_list):
            # Add base items batch
            base_end = min(b_idx + base_step, len(base_list))
            if b_idx < base_end:
                result.extend(base_list[b_idx:base_end])
                b_idx = base_end
            
            # Add persona items batch
            persona_end = min(p_idx + persona_step, len(persona_list))
            if p_idx < persona_end:
                result.extend(persona_list[p_idx:persona_end])
                p_idx = persona_end
        
        return result
    
    def _create_merge_cache_key(
        self, 
        base_config: Dict[str, Any], 
        persona_config: Dict[str, Any], 
        weight: float
    ) -> str:
        """Create cache key for merge operation.
        
        Uses content hashing to create stable keys that account for
        configuration changes while being fast to compute.
        
        Args:
            base_config: Base configuration dictionary
            persona_config: Persona configuration dictionary
            weight: Inheritance weight
            
        Returns:
            SHA256 hash as cache key
        """
        # Create stable hash from sorted JSON representation
        base_json = json.dumps(base_config, sort_keys=True, ensure_ascii=True)
        persona_json = json.dumps(persona_config, sort_keys=True, ensure_ascii=True)
        weight_str = f"{weight:.6f}"  # Fixed precision for consistent hashing
        
        # Combine all components
        combined = f"{base_json}|{persona_json}|{weight_str}"
        
        # Return SHA256 hash (first 16 chars for efficiency)
        return f"merge:{hashlib.sha256(combined.encode('utf-8')).hexdigest()[:16]}"
    
    def get_merge_stats(self) -> Dict[str, Any]:
        """Get merge operation statistics.
        
        Returns:
            Dictionary with cache hit/miss ratios and performance metrics
        """
        total_requests = self._merge_stats["cache_hits"] + self._merge_stats["cache_misses"]
        hit_rate = self._merge_stats["cache_hits"] / max(1, total_requests)
        
        return {
            **self._merge_stats,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "cache_efficiency": hit_rate * 100,
        }
    
    def clear_cache(self) -> None:
        """Clear merge operation cache."""
        # Clear only merge-related cache entries
        cache_keys_to_remove = [
            key for key in self.cache._cache.keys() 
            if key.startswith("merge:")
        ]
        
        with self.cache._lock:
            for key in cache_keys_to_remove:
                self.cache._cache.pop(key, None)
        
        # Reset stats
        self._merge_stats = {"cache_hits": 0, "cache_misses": 0, "computations": 0}


def create_inheritance_calculator(
    base_importance: float = 0.7,
    specialization_level: int = 2,
    min_weight: float = 0.01,
    max_weight: float = 1.0
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


def kl_blend_profiles(
    base_profile: "Any",
    persona_profile: "Any",
) -> "Any":
    """Blend two BehavioralProfiles using KL-divergence minimizing mixture.

    weight = base_importance / (specialization_level ** 2), clamped to [0.01, 1.0]

    Args:
        base_profile: A BehavioralProfile acting as the parent/base.
        persona_profile: A BehavioralProfile acting as the child/persona.

    Returns:
        A new BehavioralProfile representing the blended identity.
    """
    # Lazy import to avoid circular imports
    from .profile import BehavioralProfile
    from .distribution import BehavioralDistribution
    from .taxonomy import list_dimensions

    _MIN_WEIGHT = 0.01
    _MAX_WEIGHT = 1.0

    raw_weight = base_profile.base_importance / (persona_profile.specialization_level ** 2)
    weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, raw_weight))

    blended_dists: dict[str, BehavioralDistribution] = {}
    for dim in list_dimensions():
        base_dist = base_profile.distributions.get(dim, BehavioralDistribution.uniform(dim))
        persona_dist = persona_profile.distributions.get(dim, BehavioralDistribution.uniform(dim))
        blended_dists[dim] = base_dist.kl_blend(persona_dist, weight)

    return BehavioralProfile(
        agent_id=persona_profile.agent_id,
        level=persona_profile.level,
        distributions=blended_dists,
        parent_id=base_profile.agent_id,
        specialization_level=persona_profile.specialization_level,
        base_importance=persona_profile.base_importance,
        description=persona_profile.description,
        observation_count=persona_profile.observation_count,
        last_negotiation=persona_profile.last_negotiation,
        created=persona_profile.created,
        schema_version=persona_profile.schema_version,
    )
