"""Configuration management for Helios MCP server."""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import yaml
import logging
import datetime
from dataclasses import dataclass

from .atomic_ops import atomic_write_yaml

logger = logging.getLogger(__name__)


@dataclass
class HeliosConfig:
    """Helios configuration structure."""
    base_path: Path
    personas_path: Path
    learned_path: Path
    temporary_path: Path
    
    @classmethod
    def default(cls) -> "HeliosConfig":
        """Create default configuration paths."""
        base_path = Path.home() / ".helios"
        return cls(
            base_path=base_path / "base",
            personas_path=base_path / "personas",
            learned_path=base_path / "learned",
            temporary_path=base_path / "temporary",
        )
    
    def ensure_directories(self) -> None:
        """Create configuration directories if they don't exist."""
        for path in [self.base_path, self.personas_path, self.learned_path, self.temporary_path]:
            path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {path}")


class ConfigLoader:
    """Handles loading and saving YAML configuration files."""
    
    def __init__(self, config: HeliosConfig) -> None:
        self.config = config
        self.config.ensure_directories()
    
    async def load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Load YAML file asynchronously.
        
        Args:
            file_path: Path to YAML file
            
        Returns:
            Loaded configuration dictionary
            
        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        try:
            with file_path.open('r', encoding='utf-8') as f:
                content = yaml.safe_load(f) or {}
            logger.debug(f"Loaded YAML from {file_path}")
            return content
        except FileNotFoundError:
            logger.warning(f"Configuration file not found: {file_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {file_path}: {e}")
            raise
    
    async def save_yaml(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Save data to YAML file atomically.
        
        Uses atomic write operations to prevent corruption on crash.
        
        Args:
            file_path: Path to save YAML file
            data: Data to save
        """
        try:
            atomic_write_yaml(file_path, data)
            logger.debug(f"Atomically saved YAML to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save YAML file {file_path}: {e}")
            raise
    
    async def load_base_config(self) -> Dict[str, Any]:
        """Load base configuration, preferring identity.yaml.
        
        Returns:
            Base configuration dictionary
        """
        # Try identity.yaml first, then fall back to config.yaml
        identity_file = self.config.base_path / "identity.yaml"
        config_file = self.config.base_path / "config.yaml"
        
        try:
            if identity_file.exists():
                return await self.load_yaml(identity_file)
            else:
                return await self.load_yaml(config_file)
        except FileNotFoundError:
            # Create default identity.yaml based on sample
            default_config = {
                "base_importance": 0.7,
                "identity": {
                    "role": "Technical research partner and implementation specialist",
                    "expertise": ["AI/ML systems", "distributed computing", "research methodology", "software architecture"],
                    "values": [
                        "Precision over perfection",
                        "Evidence-based decisions",
                        "Incremental progress",
                        "User sovereignty",
                        "Privacy by design"
                    ]
                },
                "communication": {
                    "tone": "Direct and collegial",
                    "style": "Technical precision with practical focus",
                    "approach": [
                        "Ask clarifying questions early",
                        "Provide actionable recommendations",
                        "Explain reasoning when relevant",
                        "Challenge assumptions constructively"
                    ],
                    "preferences": [
                        "Concise responses over verbose explanations",
                        "Code examples over theoretical discussion",
                        "Working solutions over perfect abstractions"
                    ]
                },
                "behaviors": {
                    "problem_solving": {
                        "approach": "Break complex problems into testable components",
                        "methodology": "Hypothesis, test, iterate",
                        "validation": "Always verify assumptions with evidence"
                    },
                    "decision_making": {
                        "priority": "User goals over system elegance",
                        "risk_tolerance": "Conservative with user data, aggressive with implementation",
                        "trade_offs": "Ship working code over theoretical perfection"
                    },
                    "learning": {
                        "pattern": "Learn from repetition, codify successful approaches",
                        "adaptation": "Update methods based on outcomes",
                        "memory": "Version control all behavioral changes"
                    }
                },
                "technical": {
                    "languages": ["Python", "Rust", "TypeScript"],
                    "tools": ["UV over pip", "Git for everything", "Local-first architecture"],
                    "principles": [
                        "Type safety where possible",
                        "Async/await for I/O operations",
                        "Configuration over code generation",
                        "Edit existing files over creating new ones"
                    ]
                },
                "error_handling": {
                    "approach": "Fail fast, recover gracefully",
                    "logging": "Context-rich error messages",
                    "user_communication": "Clear explanation with actionable next steps"
                },
                "version": "1.0.0",
                "created": datetime.datetime.now().strftime("%Y-%m-%d"),
                "description": "Base identity providing fundamental behaviors for all specialized personas"
            }
            # Save default identity config for future use using atomic operations
            atomic_write_yaml(identity_file, default_config)
            return default_config
    
    async def load_persona_config(self, persona_name: str) -> Optional[Dict[str, Any]]:
        """Load specific persona configuration.
        
        Args:
            persona_name: Name of the persona
            
        Returns:
            Persona configuration dictionary or None if not found
        """
        persona_file = self.config.personas_path / f"{persona_name}.yaml"
        try:
            return await self.load_yaml(persona_file)
        except FileNotFoundError:
            logger.info(f"Persona '{persona_name}' not found")
            return None
    
    async def list_personas(self) -> list[str]:
        """List available personas.
        
        Returns:
            List of persona names (without .yaml extension)
        """
        try:
            yaml_files = list(self.config.personas_path.glob("*.yaml"))
            return [f.stem for f in yaml_files]
        except Exception as e:
            logger.error(f"Failed to list personas: {e}")
            return []
    
    async def batch_load_personas(self, persona_names: list[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Load multiple personas concurrently.
        
        Args:
            persona_names: List of persona names to load
            
        Returns:
            Dictionary mapping persona names to their configurations
        """
        async def load_single(name: str) -> Tuple[str, Optional[Dict[str, Any]]]:
            config = await self.load_persona_config(name)
            return name, config
        
        # Load all personas concurrently
        tasks = [load_single(name) for name in persona_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results, filtering out exceptions
        persona_configs = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Failed to load persona in batch: {result}")
                continue
            name, config = result
            persona_configs[name] = config
        
        return persona_configs
    
    async def preload_common_configs(self) -> None:
        """Preload commonly used configurations into cache.
        
        This method loads the base config and all available personas
        to warm up the cache for better performance.
        """
        try:
            # Load base config
            _ = await self.load_base_config()
            
            # Get list of personas and load them
            personas = await self.list_personas()
            if personas:
                await self.batch_load_personas(personas)
            
            logger.info(f"Preloaded {len(personas)} personas and base config")
        except Exception as e:
            logger.warning(f"Failed to preload configs: {e}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.cache.start_cleanup_task()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        self._thread_pool.shutdown(wait=True)
        # Note: Don't shutdown cache here as it may be shared
