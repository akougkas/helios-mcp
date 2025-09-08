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
from .security import (
    validate_persona_name,
    validate_config_key,
    validate_parameter_name,
    validate_commits_back,
    sanitize_git_message,
    validate_file_path,
    sanitize_error_message,
    SecurityError,
    PathTraversalError,
    InvalidInputError
)

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
            
        Raises:
            InvalidInputError: If config name is invalid
            PathTraversalError: If path traversal is attempted
        """
        if config_name == "base":
            config_path = self.helios_dir / "base" / "identity.yaml"
        else:
            # Validate persona name to prevent path traversal
            validated_name = validate_persona_name(config_name)
            config_path = self.helios_dir / "personas" / f"{validated_name}.yaml"
        
        # Validate the final path is within helios directory
        return validate_file_path(config_path, self.helios_dir)
    
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
            # Validate input parameters
            try:
                validated_persona = validate_persona_name(params.persona)
                validated_key = validate_config_key(params.key)
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid learning parameters: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid input: {sanitize_error_message(e)}"
                }
            
            # Load persona configuration with safe path
            persona_path = validate_file_path(
                self.helios_dir / "personas" / f"{validated_persona}.yaml",
                self.helios_dir
            )
            if not persona_path.exists():
                return {
                    "status": "error",
                    "error": f"Persona '{validated_persona}' not found"
                }
            
            with open(persona_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            # Navigate to the key location using validated key
            parent, final_key = self._navigate_to_key(config, validated_key)
            
            # Capture old value for history
            old_value = parent.get(final_key, "not set")
            
            # Set new value (additive, not replacive for lists) - ensure proper copying
            if isinstance(old_value, list) and isinstance(params.value, (str, int, float)):
                # Create a proper copy of the list to avoid modification issues
                new_list = old_value.copy()
                if params.value not in new_list:
                    new_list.append(params.value)
                    parent[final_key] = new_list
                    logger.info(f"Added {params.value} to {params.key} list")
                else:
                    logger.info(f"Value {params.value} already exists in {params.key} list, no change made")
            else:
                # Direct assignment for other types
                parent[final_key] = params.value
            
            # Save with atomic write
            atomic_write_yaml(persona_path, config)
            
            # Git commit with sanitized message
            commit_msg = sanitize_git_message(
                f"Learned: {validated_key}={params.value} for {validated_persona} persona"
            )
            self.git_store.auto_commit(commit_msg)
            
            logger.info(f"Learned behavior: {validated_key} for {validated_persona}")
            
            return {
                "status": "learned",
                "persona": validated_persona,
                "key": validated_key,
                "old_value": old_value,
                "new_value": parent[final_key],
                "message": "Behavior learned and committed to git"
            }
            
        except Exception as e:
            logger.error(f"Failed to learn behavior: {e}")
            return {
                "status": "error",
                "error": sanitize_error_message(e)
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
            # Validate input parameters
            try:
                validated_parameter = validate_parameter_name(params.parameter)
                
                # Validate target - 'base' is allowed, others must be valid persona names
                if params.target == "base":
                    validated_target = "base"
                else:
                    validated_target = validate_persona_name(params.target)
                    
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid tuning parameters: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid input: {sanitize_error_message(e)}"
                }
            
            # Determine target file and valid parameters
            try:
                config_path = self._get_config_path(validated_target)
            except (SecurityError, PathTraversalError) as e:
                logger.warning(f"Invalid config path: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid configuration target: {sanitize_error_message(e)}"
                }
            
            if validated_target == "base":
                valid_params = ["base_importance"]
                if validated_parameter not in valid_params:
                    return {
                        "status": "error",
                        "error": f"Cannot tune '{validated_parameter}' for base configuration"
                    }
                # Validate base_importance range
                if not 0.0 <= params.value <= 1.0:
                    return {
                        "status": "error",
                        "error": "base_importance must be between 0.0 and 1.0"
                    }
            else:
                valid_params = ["specialization_level"]
                if validated_parameter not in valid_params:
                    return {
                        "status": "error",
                        "error": f"Cannot tune '{validated_parameter}' for persona configuration"
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
                    "error": f"Configuration '{validated_target}' not found"
                }
            
            # Load and update configuration
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            old_value = config.get(validated_parameter, "not set")
            config[validated_parameter] = params.value
            
            # Calculate new inheritance weight if applicable
            inheritance_info = ""
            if validated_parameter == "specialization_level":
                # Load actual base_importance from base configuration
                try:
                    base_config_path = self.helios_dir / "base" / "identity.yaml"
                    if base_config_path.exists():
                        with open(base_config_path, 'r', encoding='utf-8') as f:
                            base_config = yaml.safe_load(f) or {}
                        base_importance = base_config.get('base_importance', 0.7)  # fallback to 0.7
                    else:
                        base_importance = 0.7  # default if no base config exists
                        logger.warning("Base config not found, using default base_importance=0.7")
                        
                    new_weight = base_importance / (params.value ** 2)
                    inheritance_info = f" (inheritance weight: {new_weight:.1%})"
                    logger.debug(f"Calculated inheritance weight using base_importance={base_importance}")
                except Exception as e:
                    logger.warning(f"Could not load base config for weight calculation: {e}, using default")
                    base_importance = 0.7
                    new_weight = base_importance / (params.value ** 2)
                    inheritance_info = f" (inheritance weight: {new_weight:.1%})"
            
            # Save with atomic write
            atomic_write_yaml(config_path, config)
            
            # Git commit with sanitized message
            commit_msg = sanitize_git_message(
                f"Tuned: {validated_parameter} from {old_value} to {params.value}{inheritance_info}"
            )
            self.git_store.auto_commit(commit_msg)
            
            logger.info(f"Tuned {validated_parameter} for {validated_target}")
            
            return {
                "status": "tuned",
                "target": validated_target,
                "parameter": validated_parameter,
                "old_value": old_value,
                "new_value": params.value,
                "inheritance_info": inheritance_info.strip(),
                "message": "Weight tuned and committed to git"
            }
            
        except Exception as e:
            logger.error(f"Failed to tune weight: {e}")
            return {
                "status": "error",
                "error": sanitize_error_message(e)
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
            # Validate commits_back parameter to prevent injection
            try:
                validated_commits = validate_commits_back(params.commits_back)
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid revert parameters: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid input: {sanitize_error_message(e)}"
                }
            
            # Get recent commits to show what will be reverted - use safe command construction
            helios_dir_str = str(self.helios_dir.resolve())
            commits_str = str(validated_commits)
            
            result = subprocess.run(
                ["git", "-C", helios_dir_str, "log", "--oneline", f"-{commits_str}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10  # Add timeout for safety
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
            
            # Check for uncommitted changes before reverting
            status_result = subprocess.run(
                ["git", "-C", helios_dir_str, "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10  # Add timeout for safety
            )
            
            if status_result.returncode == 0 and status_result.stdout.strip():
                return {
                    "status": "error",
                    "error": "Cannot revert: repository has uncommitted changes. Please commit or stash changes first."
                }

            # Perform the revert with corrected range syntax
            if validated_commits == 1:
                # Single commit revert
                result = subprocess.run(
                    ["git", "-C", helios_dir_str, "revert", "HEAD", "--no-edit"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30  # Add timeout for safety
                )
            else:
                # Multiple commits revert - use correct range syntax
                revert_range = f"HEAD~{validated_commits-1}..HEAD"
                result = subprocess.run(
                    ["git", "-C", helios_dir_str, "revert", revert_range, "--no-edit"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30  # Add timeout for safety
                )
                
                # If range revert fails, try individual reverts in reverse order
                if result.returncode != 0:
                    logger.info("Range revert failed, attempting individual commit reverts")
                    failed_reverts = []
                    
                    for i in range(validated_commits):
                        commit_ref = f"HEAD~{i}"
                        individual_result = subprocess.run(
                            ["git", "-C", helios_dir_str, "revert", commit_ref, "--no-edit"],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=30  # Add timeout for safety
                        )
                        if individual_result.returncode != 0:
                            failed_reverts.append(f"{commit_ref}: {individual_result.stderr}")
                    
                    if failed_reverts:
                        return {
                            "status": "error",
                            "error": f"Git revert failed for commits: {'; '.join(failed_reverts)}"
                        }
                    else:
                        result = individual_result  # Use last successful result
            
            if result.returncode != 0:
                # Check if it's a merge conflict
                if "conflict" in result.stderr.lower():
                    return {
                        "status": "error",
                        "error": f"Git revert failed due to conflicts: {result.stderr}. Please resolve conflicts manually."
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Git revert failed: {result.stderr}"
                    }
            
            logger.info(f"Reverted {validated_commits} commits")
            
            return {
                "status": "reverted",
                "commits_reverted": validated_commits,
                "reverted_commits": commits_to_revert,
                "message": f"Successfully reverted {validated_commits} commit(s)"
            }
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"Git operation timed out: {e}")
            return {
                "status": "error",
                "error": "Git operation timed out"
            }
        except Exception as e:
            logger.error(f"Failed to revert learning: {e}")
            return {
                "status": "error",
                "error": sanitize_error_message(e)
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
            # Validate input parameters
            try:
                validated_key = validate_config_key(params.key)
                
                # Validate from_config - 'base' is allowed, others must be valid persona names
                if params.from_config == "base":
                    validated_from = "base"
                else:
                    validated_from = validate_persona_name(params.from_config)
                    
                # Validate to_config - 'base' is allowed, others must be valid persona names  
                if params.to_config == "base":
                    validated_to = "base"
                else:
                    validated_to = validate_persona_name(params.to_config)
                    
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid evolution parameters: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid input: {sanitize_error_message(e)}"
                }
            
            # Validate source and target are different
            if validated_from == validated_to:
                return {
                    "status": "error",
                    "error": "Source and target must be different"
                }
            
            # Load source configuration with path validation
            try:
                from_path = self._get_config_path(validated_from)
            except (SecurityError, PathTraversalError) as e:
                logger.warning(f"Invalid source config path: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid source configuration: {sanitize_error_message(e)}"
                }
                
            if not from_path.exists():
                return {
                    "status": "error",
                    "error": f"Source configuration '{validated_from}' not found"
                }
            
            with open(from_path, 'r', encoding='utf-8') as f:
                from_config = yaml.safe_load(f) or {}
            
            # Extract the value from source using validated key
            try:
                parent, final_key = self._navigate_to_key(from_config, validated_key, create_missing=False)
                if final_key not in parent:
                    return {
                        "status": "error",
                        "error": f"Key '{validated_key}' not found in {validated_from}"
                    }
                value = parent[final_key]
                
                # Remove from source
                del parent[final_key]
                
                # Clean up empty parent dicts
                keys = validated_key.split('.')
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
            
            # Load target configuration with path validation
            try:
                to_path = self._get_config_path(validated_to)
            except (SecurityError, PathTraversalError) as e:
                logger.warning(f"Invalid target config path: {e}")
                return {
                    "status": "error",
                    "error": f"Invalid target configuration: {sanitize_error_message(e)}"
                }
            if not to_path.exists():
                # Create new persona if it doesn't exist
                to_config = {
                    "specialization_level": 2,
                    "behaviors": {},
                    "description": f"Evolved from {validated_from}"
                }
            else:
                with open(to_path, 'r', encoding='utf-8') as f:
                    to_config = yaml.safe_load(f) or {}
            
            # Add to target using validated key
            parent, final_key = self._navigate_to_key(to_config, validated_key)
            parent[final_key] = value
            
            # Save both configurations atomically
            atomic_write_yaml(from_path, from_config)
            atomic_write_yaml(to_path, to_config)
            
            # Git commit the evolution with sanitized message
            direction = "promoted" if validated_to == "base" else "specialized"
            commit_msg = sanitize_git_message(
                f"Evolved: {validated_key} {direction} from {validated_from} to {validated_to}"
            )
            self.git_store.auto_commit(commit_msg)
            
            logger.info(f"Evolved behavior {validated_key} from {validated_from} to {validated_to}")
            
            return {
                "status": "evolved",
                "key": validated_key,
                "value": value,
                "from": validated_from,
                "to": validated_to,
                "direction": direction,
                "message": f"Behavior {direction} and committed to git"
            }
            
        except Exception as e:
            logger.error(f"Failed to evolve behavior: {e}")
            return {
                "status": "error",
                "error": sanitize_error_message(e)
            }