"""Configuration validation for Helios MCP server.

Validates and recovers corrupted configurations.
Ensures data integrity and provides clear error messages.
"""

import yaml
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .atomic_ops import atomic_write_yaml

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates and recovers corrupted configurations.
    
    Features:
    - Validate YAML syntax and required fields
    - Check value ranges (base_importance 0.0-1.0, specialization_level >= 1)
    - Recover from git if corrupted
    - Create defaults if recovery fails
    - Return clear error messages
    """
    
    def __init__(self, helios_dir: Path):
        """
        Args:
            helios_dir: Path to Helios configuration directory
        """
        self.helios_dir = helios_dir
        self.base_path = helios_dir / "base"
        self.personas_path = helios_dir / "personas"
        self.learned_path = helios_dir / "learned"
        self.temporary_path = helios_dir / "temporary"
    
    def validate_base_config(self, data: dict) -> Tuple[bool, Optional[str]]:
        """Validate base configuration data.
        
        Args:
            data: Configuration data dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check required fields
            if "base_importance" not in data:
                return False, "Missing required field: base_importance"
            
            # Validate base_importance range
            base_importance = data["base_importance"]
            if not isinstance(base_importance, (int, float)):
                return False, f"base_importance must be a number, got {type(base_importance).__name__}"
            
            if not (0.0 <= base_importance <= 1.0):
                return False, f"base_importance must be between 0.0 and 1.0, got {base_importance}"
            
            # Check optional but expected fields
            expected_sections = ["identity", "communication", "behaviors", "technical"]
            for section in expected_sections:
                if section in data and not isinstance(data[section], dict):
                    return False, f"Section '{section}' must be a dictionary"
            
            # Validate version if present
            if "version" in data:
                version = data["version"]
                if not isinstance(version, str):
                    return False, f"version must be a string, got {type(version).__name__}"
            
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def validate_persona_config(self, data: dict) -> Tuple[bool, Optional[str]]:
        """Validate persona configuration data.
        
        Args:
            data: Persona configuration data dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check required fields
            if "specialization_level" not in data:
                return False, "Missing required field: specialization_level"
            
            # Validate specialization_level
            spec_level = data["specialization_level"]
            if not isinstance(spec_level, (int, float)):
                return False, f"specialization_level must be a number, got {type(spec_level).__name__}"
            
            if spec_level < 1:
                return False, f"specialization_level must be >= 1, got {spec_level}"
            
            # Check for name if present
            if "name" in data:
                name = data["name"]
                if not isinstance(name, str) or not name.strip():
                    return False, "name must be a non-empty string"
            
            # Check for description if present
            if "description" in data:
                description = data["description"]
                if not isinstance(description, str):
                    return False, f"description must be a string, got {type(description).__name__}"
            
            # Validate specializations section if present
            if "specializations" in data:
                specializations = data["specializations"]
                if not isinstance(specializations, dict):
                    return False, "specializations must be a dictionary"
            
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def validate_yaml_syntax(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """Validate YAML file syntax.
        
        Args:
            file_path: Path to YAML file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not file_path.exists():
                return False, f"File does not exist: {file_path}"
            
            with file_path.open('r', encoding='utf-8') as f:
                yaml.safe_load(f)
            
            return True, None
            
        except yaml.YAMLError as e:
            return False, f"YAML syntax error: {e}"
        except Exception as e:
            return False, f"Error reading file: {e}"
    
    def recover_from_corruption(self, file_path: Path) -> bool:
        """Attempt to recover corrupted configuration from git or create defaults.
        
        Args:
            file_path: Path to corrupted configuration file
            
        Returns:
            True if recovery was successful, False otherwise
        """
        try:
            logger.info(f"Attempting to recover {file_path} from git")
            
            # Check if we're in a git repository
            git_dir = self.helios_dir / ".git"
            git_recovery_successful = False
            
            if git_dir.exists():
                # Get relative path from helios directory
                try:
                    rel_path = file_path.relative_to(self.helios_dir)
                except ValueError:
                    logger.error(f"File {file_path} is not within Helios directory")
                    return False
                
                # Try to restore from git HEAD
                result = subprocess.run([
                    "git", "-C", str(self.helios_dir),
                    "checkout", "HEAD", "--", str(rel_path)
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"Successfully recovered {file_path} from git")
                    return True
                else:
                    logger.warning(f"Git recovery failed: {result.stderr}")
            else:
                logger.warning("No git repository found, cannot recover from git")
            
            # If git recovery failed or not available, try to create defaults
            logger.info(f"Attempting to create default configuration for {file_path}")
            
            # Determine if this is a base or persona config based on path
            if "base" in file_path.parts and file_path.name == "identity.yaml":
                return self.create_default_base_config(file_path)
            elif "personas" in file_path.parts and file_path.suffix == ".yaml":
                persona_name = file_path.stem
                return self.create_default_persona_config(file_path, persona_name)
            else:
                logger.error(f"Cannot create default for unknown config type: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error during recovery: {e}")
            return False
    
    def create_default_base_config(self, file_path: Path) -> bool:
        """Create a default base configuration.
        
        Args:
            file_path: Path where to create the default config
            
        Returns:
            True if creation was successful, False otherwise
        """
        try:
            default_config = {
                "base_importance": 0.7,
                "identity": {
                    "role": "Technical research partner and implementation specialist",
                    "expertise": [
                        "AI/ML systems",
                        "distributed computing", 
                        "research methodology",
                        "software architecture"
                    ]
                },
                "communication": {
                    "tone": "Direct and collegial",
                    "style": "Technical precision with practical focus"
                },
                "behaviors": {
                    "problem_solving": {
                        "approach": "Break complex problems into testable components",
                        "methodology": "Hypothesis, test, iterate"
                    }
                },
                "version": "1.0.0",
                "description": "Base identity providing fundamental behaviors for all specialized personas"
            }
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use atomic write
            atomic_write_yaml(file_path, default_config)
            
            logger.info(f"Created default base configuration at {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create default base config: {e}")
            return False
    
    def create_default_persona_config(self, file_path: Path, name: str) -> bool:
        """Create a default persona configuration.
        
        Args:
            file_path: Path where to create the default config
            name: Name of the persona
            
        Returns:
            True if creation was successful, False otherwise
        """
        try:
            default_config = {
                "name": name,
                "specialization_level": 1.5,
                "description": f"Specialized persona: {name}",
                "specializations": {
                    "focus_area": "General assistance",
                    "approach": "Balanced technical and user-focused"
                },
                "version": "1.0.0"
            }
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use atomic write
            atomic_write_yaml(file_path, default_config)
            
            logger.info(f"Created default persona configuration for '{name}' at {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create default persona config: {e}")
            return False
    
    def validate_all_configs(self, helios_dir: Path) -> List[str]:
        """Validate all configuration files in Helios directory.
        
        Args:
            helios_dir: Path to Helios configuration directory
            
        Returns:
            List of error messages (empty if all valid)
        """
        errors = []
        
        try:
            # Validate base configurations
            base_files = ["identity.yaml", "config.yaml"]
            for base_file in base_files:
                file_path = self.base_path / base_file
                if file_path.exists():
                    # Check YAML syntax first
                    is_valid, error = self.validate_yaml_syntax(file_path)
                    if not is_valid:
                        errors.append(f"Base config {base_file}: {error}")
                        # Attempt recovery
                        if self.recover_from_corruption(file_path):
                            # Re-validate after recovery
                            is_valid, error = self.validate_yaml_syntax(file_path)
                            if is_valid:
                                logger.info(f"Successfully recovered {base_file}")
                            else:
                                errors.append(f"Recovery failed for {base_file}: {error}")
                        continue
                    
                    # Load and validate content
                    try:
                        with file_path.open('r', encoding='utf-8') as f:
                            data = yaml.safe_load(f) or {}
                        
                        is_valid, error = self.validate_base_config(data)
                        if not is_valid:
                            errors.append(f"Base config {base_file}: {error}")
                    
                    except Exception as e:
                        errors.append(f"Base config {base_file}: Error loading content - {e}")
            
            # Validate persona configurations
            if self.personas_path.exists():
                for persona_file in self.personas_path.glob("*.yaml"):
                    # Check YAML syntax first
                    is_valid, error = self.validate_yaml_syntax(persona_file)
                    if not is_valid:
                        errors.append(f"Persona {persona_file.name}: {error}")
                        # Attempt recovery
                        if self.recover_from_corruption(persona_file):
                            # Re-validate after recovery
                            is_valid, error = self.validate_yaml_syntax(persona_file)
                            if is_valid:
                                logger.info(f"Successfully recovered {persona_file.name}")
                            else:
                                errors.append(f"Recovery failed for {persona_file.name}: {error}")
                        continue
                    
                    # Load and validate content
                    try:
                        with persona_file.open('r', encoding='utf-8') as f:
                            data = yaml.safe_load(f) or {}
                        
                        is_valid, error = self.validate_persona_config(data)
                        if not is_valid:
                            errors.append(f"Persona {persona_file.name}: {error}")
                    
                    except Exception as e:
                        errors.append(f"Persona {persona_file.name}: Error loading content - {e}")
            
            # Check for missing base configuration
            identity_file = self.base_path / "identity.yaml"
            config_file = self.base_path / "config.yaml"
            
            if not identity_file.exists() and not config_file.exists():
                logger.warning("No base configuration found, creating default")
                if self.create_default_base_config(identity_file):
                    logger.info("Default base configuration created successfully")
                else:
                    errors.append("Failed to create default base configuration")
            
        except Exception as e:
            errors.append(f"Validation process error: {e}")
        
        return errors
