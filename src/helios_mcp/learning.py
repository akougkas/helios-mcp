"""Learning system for Helios MCP - Direct configuration evolution through use.

The learning system embodies the gravitational metaphor: when new behaviors are learned,
they don't erase existing ones but shift the dynamics of the entire system. Like celestial
bodies, each behavior has mass (importance) and influences others through the inheritance
model's gravitational pull.

Learning is not replacement - it's evolution through accumulation.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Union, List
from pydantic import BaseModel, Field
import yaml

from .atomic_ops import atomic_write_yaml
from .config import HeliosConfig, ConfigLoader
from .git_store import GitStore

logger = logging.getLogger(__name__)


class LearnBehaviorParams(BaseModel):
    """Parameters for learning a new behavior."""
    persona: str = Field(description="Name of persona to learn in")
    key: str = Field(description="Dot-notation key (e.g., 'behaviors.tools.package_manager')")
    value: Any = Field(description="Value to set (can be string, list, dict, etc.)")


class TuneWeightParams(BaseModel):
    """Parameters for tuning inheritance weights."""
    target: str = Field(description="Target config: 'base' or persona name")
    parameter: str = Field(description="Parameter to tune: 'base_importance' or 'specialization_level'")
    value: float = Field(description="New value (0.0-1.0 for base_importance, >=1 for specialization_level)")


class RevertLearningParams(BaseModel):
    """Parameters for reverting recent learning."""
    commits_back: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of commits to revert (1-10)"
    )


class EvolveBehaviorParams(BaseModel):
    """Parameters for evolving behaviors between configurations."""
    from_config: str = Field(description="Source config: 'base' or persona name")
    to_config: str = Field(description="Target config: 'base' or persona name")  
    key: str = Field(description="Dot-notation key to move (e.g., 'behaviors.package_manager')")


class LearningManager:
    """Manages learning operations - the evolution engine for AI personalities.
    
    Learning doesn't replace - it adds mass to the system. Each learned behavior
    shifts the gravitational dynamics without erasing what came before.
    """
    
    def __init__(self, helios_dir: Path):
        """Initialize the learning manager.
        
        Args:
            helios_dir: Path to Helios configuration directory
        """
        self.helios_dir = helios_dir
        
        # Create config object
        config = HeliosConfig(
            base_path=helios_dir / "base",
            personas_path=helios_dir / "personas",
            learned_path=helios_dir / "learned",
            temporary_path=helios_dir / "temporary"
        )
        
        self.config_loader = ConfigLoader(config)
        self.git_store = GitStore(helios_dir)
    
    def _navigate_to_key(self, config: Dict, key: str, create_missing: bool = True) -> tuple[Dict, str]:
        """Navigate to a nested key in config, creating path if needed.
        
        Args:
            config: Configuration dictionary
            key: Dot-notation key path
            create_missing: Whether to create missing intermediate keys
            
        Returns:
            Tuple of (parent_dict, final_key)
        """
        keys = key.split('.')
        target = config
        
        # Navigate to parent of final key
        for k in keys[:-1]:
            if k not in target:
                if create_missing:
                    target[k] = {}
                else:
                    raise KeyError(f"Path '{k}' not found in configuration")
            target = target[k]
            
        return target, keys[-1]
    
    def _get_config_path(self, config_name: str) -> Path:
        """Get the path to a configuration file.
        
        Args:
            config_name: 'base' or persona name
            
        Returns:
            Path to configuration file
        """
        if config_name == "base":
            return self.helios_dir / "base" / "identity.yaml"
        else:
            return self.helios_dir / "personas" / f"{config_name}.yaml"
    
    async def learn_behavior(self, params: LearnBehaviorParams) -> Dict[str, Any]:
        """Learn a new behavior by directly editing persona configuration.
        
        This adds mass to the system - the new behavior doesn't erase others
        but shifts the gravitational dynamics through the inheritance model.
        
        Args:
            params: Learning parameters
            
        Returns:
            Learning result with old and new values
        """
        try:
            # Load persona configuration
            persona_path = self.helios_dir / "personas" / f"{params.persona}.yaml"
            if not persona_path.exists():
                return {
                    "status": "error",
                    "error": f"Persona '{params.persona}' not found"
                }
            
            with open(persona_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            # Navigate to the key location
            parent, final_key = self._navigate_to_key(config, params.key)
            
            # Capture old value for history
            old_value = parent.get(final_key, "not set")
            
            # Set new value (additive, not replacive for lists)
            if isinstance(old_value, list) and isinstance(params.value, (str, int, float)):
                # Add to list rather than replace
                if params.value not in old_value:
                    parent[final_key] = old_value + [params.value]
                    logger.info(f"Added {params.value} to {params.key} list")
            else:
                # Direct assignment for other types
                parent[final_key] = params.value
            
            # Save with atomic write
            atomic_write_yaml(persona_path, config)
            
            # Git commit with semantic message
            commit_msg = f"Learned: {params.key}={params.value} for {params.persona} persona"
            self.git_store.auto_commit(commit_msg)
            
            logger.info(f"Learned behavior: {params.key} for {params.persona}")
            
            return {
                "status": "learned",
                "persona": params.persona,
                "key": params.key,
                "old_value": old_value,
                "new_value": parent[final_key],
                "message": "Behavior learned and committed to git"
            }
            
        except Exception as e:
            logger.error(f"Failed to learn behavior: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def tune_weight(self, params: TuneWeightParams) -> Dict[str, Any]:
        """Adjust inheritance weights to shift the gravitational dynamics.
        
        Tuning weights changes how strongly the base influences personas,
        like adjusting the mass of celestial bodies in the system.
        
        Args:
            params: Tuning parameters
            
        Returns:
            Tuning result with old and new values
        """
        try:
            # Determine target file and valid parameters
            config_path = self._get_config_path(params.target)
            
            if params.target == "base":
                valid_params = ["base_importance"]
                if params.parameter not in valid_params:
                    return {
                        "status": "error",
                        "error": f"Cannot tune '{params.parameter}' for base configuration"
                    }
                # Validate base_importance range
                if not 0.0 <= params.value <= 1.0:
                    return {
                        "status": "error",
                        "error": "base_importance must be between 0.0 and 1.0"
                    }
            else:
                valid_params = ["specialization_level"]
                if params.parameter not in valid_params:
                    return {
                        "status": "error",
                        "error": f"Cannot tune '{params.parameter}' for persona configuration"
                    }
                # Validate specialization_level range
                if params.value < 1.0:
                    return {
                        "status": "error",
                        "error": "specialization_level must be >= 1.0"
                    }
            
            if not config_path.exists():
                return {
                    "status": "error",
                    "error": f"Configuration '{params.target}' not found"
                }
            
            # Load and update configuration
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            old_value = config.get(params.parameter, "not set")
            config[params.parameter] = params.value
            
            # Calculate new inheritance weight if applicable
            inheritance_info = ""
            if params.parameter == "specialization_level":
                # For now, just assume default base_importance of 0.7
                # Could make this async and await load_base_config() if needed
                base_importance = 0.7
                new_weight = base_importance / (params.value ** 2)
                inheritance_info = f" (inheritance weight: {new_weight:.1%})"
            
            # Save with atomic write
            atomic_write_yaml(config_path, config)
            
            # Git commit
            commit_msg = f"Tuned: {params.parameter} from {old_value} to {params.value}{inheritance_info}"
            self.git_store.auto_commit(commit_msg)
            
            logger.info(f"Tuned {params.parameter} for {params.target}")
            
            return {
                "status": "tuned",
                "target": params.target,
                "parameter": params.parameter,
                "old_value": old_value,
                "new_value": params.value,
                "inheritance_info": inheritance_info.strip(),
                "message": "Weight tuned and committed to git"
            }
            
        except Exception as e:
            logger.error(f"Failed to tune weight: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def revert_learning(self, params: RevertLearningParams) -> Dict[str, Any]:
        """Undo recent learning by reverting git commits.
        
        Like rewinding time in the planetary system, returning to a previous
        gravitational configuration.
        
        Args:
            params: Revert parameters
            
        Returns:
            Revert result with affected commits
        """
        try:
            # Get recent commits to show what will be reverted
            result = subprocess.run(
                ["git", "-C", str(self.helios_dir), "log", "--oneline", f"-{params.commits_back}"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return {
                    "status": "error",
                    "error": "Failed to retrieve git history"
                }
            
            commits_to_revert = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            if not commits_to_revert:
                return {
                    "status": "error",
                    "error": "No commits to revert"
                }
            
            # Perform the revert
            result = subprocess.run(
                ["git", "-C", str(self.helios_dir), "revert", 
                 f"HEAD~{params.commits_back}..HEAD", "--no-edit"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                # Try alternative approach for single commit
                if params.commits_back == 1:
                    result = subprocess.run(
                        ["git", "-C", str(self.helios_dir), "revert", "HEAD", "--no-edit"],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                
                if result.returncode != 0:
                    return {
                        "status": "error",
                        "error": f"Git revert failed: {result.stderr}"
                    }
            
            logger.info(f"Reverted {params.commits_back} commits")
            
            return {
                "status": "reverted",
                "commits_reverted": params.commits_back,
                "reverted_commits": commits_to_revert,
                "message": f"Successfully reverted {params.commits_back} commit(s)"
            }
            
        except Exception as e:
            logger.error(f"Failed to revert learning: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def evolve_behavior(self, params: EvolveBehaviorParams) -> Dict[str, Any]:
        """Move a behavior between configurations (promotion/demotion).
        
        Like a moon moving from one planet's orbit to another, changing
        the gravitational dynamics of both systems.
        
        Args:
            params: Evolution parameters
            
        Returns:
            Evolution result
        """
        try:
            # Validate source and target are different
            if params.from_config == params.to_config:
                return {
                    "status": "error",
                    "error": "Source and target must be different"
                }
            
            # Load source configuration
            from_path = self._get_config_path(params.from_config)
            if not from_path.exists():
                return {
                    "status": "error",
                    "error": f"Source configuration '{params.from_config}' not found"
                }
            
            with open(from_path, 'r', encoding='utf-8') as f:
                from_config = yaml.safe_load(f) or {}
            
            # Extract the value from source
            try:
                parent, final_key = self._navigate_to_key(from_config, params.key, create_missing=False)
                if final_key not in parent:
                    return {
                        "status": "error",
                        "error": f"Key '{params.key}' not found in {params.from_config}"
                    }
                value = parent[final_key]
                
                # Remove from source
                del parent[final_key]
                
                # Clean up empty parent dicts
                keys = params.key.split('.')
                if len(keys) > 1:
                    # Check if parent dict is now empty and remove it
                    temp = from_config
                    for k in keys[:-1]:
                        if k in temp and not temp[k]:
                            del temp[k]
                            break
                        temp = temp.get(k, {})
                
            except KeyError as e:
                return {
                    "status": "error",
                    "error": str(e)
                }
            
            # Load target configuration
            to_path = self._get_config_path(params.to_config)
            if not to_path.exists():
                # Create new persona if it doesn't exist
                to_config = {
                    "specialization_level": 2,
                    "behaviors": {},
                    "description": f"Evolved from {params.from_config}"
                }
            else:
                with open(to_path, 'r', encoding='utf-8') as f:
                    to_config = yaml.safe_load(f) or {}
            
            # Add to target
            parent, final_key = self._navigate_to_key(to_config, params.key)
            parent[final_key] = value
            
            # Save both configurations atomically
            atomic_write_yaml(from_path, from_config)
            atomic_write_yaml(to_path, to_config)
            
            # Git commit the evolution
            direction = "promoted" if params.to_config == "base" else "specialized"
            commit_msg = f"Evolved: {params.key} {direction} from {params.from_config} to {params.to_config}"
            self.git_store.auto_commit(commit_msg)
            
            logger.info(f"Evolved behavior {params.key} from {params.from_config} to {params.to_config}")
            
            return {
                "status": "evolved",
                "key": params.key,
                "value": value,
                "from": params.from_config,
                "to": params.to_config,
                "direction": direction,
                "message": f"Behavior {direction} and committed to git"
            }
            
        except Exception as e:
            logger.error(f"Failed to evolve behavior: {e}")
            return {
                "status": "error",
                "error": str(e)
            }