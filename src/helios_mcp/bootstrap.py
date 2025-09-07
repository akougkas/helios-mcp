"""Bootstrap and installation detection for Helios MCP."""

import logging
import subprocess
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .atomic_ops import atomic_write_yaml, validate_yaml_file
from .config import HeliosConfig

logger = logging.getLogger(__name__)


class BootstrapManager:
    """Manages first installation and subsequent boots."""
    
    def __init__(self, helios_dir: Path) -> None:
        """Initialize bootstrap manager.
        
        Args:
            helios_dir: Path to Helios configuration directory
        """
        self.helios_dir = helios_dir
        self.version_file = helios_dir / ".helios_version"
        self.config = HeliosConfig(
            base_path=helios_dir / "base",
            personas_path=helios_dir / "personas", 
            learned_path=helios_dir / "learned",
            temporary_path=helios_dir / "temporary"
        )
        
    def is_first_install(self) -> bool:
        """Check if this is the first installation.
        
        Returns:
            True if this is a fresh installation
        """
        return not self.version_file.exists()
    
    def bootstrap_installation(self) -> None:
        """Bootstrap a fresh Helios installation.
        
        Creates directory structure, default configurations,
        initializes git repository, and creates version file.
        """
        try:
            logger.info("Bootstrapping fresh Helios installation")
            
            # Create directory structure
            self._create_directory_structure()
            
            # Initialize git repository if needed
            self._initialize_git_repo()
            
            # Create default base configuration
            self._create_default_base_config()
            
            # Create welcome persona
            self._create_welcome_persona()
            
            # Create version file (this marks installation as complete)
            self._create_version_file()
            
            logger.info("Helios installation bootstrap complete")
            
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            # Clean up on failure
            self._cleanup_failed_bootstrap()
            raise
    
    def get_installation_info(self) -> Dict[str, Any]:
        """Get installation information.
        
        Returns:
            Dictionary with installation details
        """
        if not self.version_file.exists():
            return {
                "installed": False,
                "version": None,
                "install_date": None
            }
        
        try:
            with self.version_file.open('r', encoding='utf-8') as f:
                import yaml
                info = yaml.safe_load(f) or {}
            
            return {
                "installed": True,
                "version": info.get("version", "unknown"),
                "install_date": info.get("install_date"),
                "last_boot": info.get("last_boot")
            }
        except Exception as e:
            logger.warning(f"Failed to read installation info: {e}")
            return {
                "installed": True,
                "version": "unknown",
                "install_date": "unknown",
                "error": str(e)
            }
    
    def update_last_boot(self) -> None:
        """Update last boot timestamp in version file."""
        try:
            info = self.get_installation_info()
            if info["installed"]:
                # Preserve existing info, just update last_boot
                version_data = {
                    "version": info.get("version", "0.1.0"),
                    "install_date": info.get("install_date"),
                    "last_boot": datetime.datetime.now().isoformat()
                }
                atomic_write_yaml(self.version_file, version_data)
                logger.debug("Updated last boot timestamp")
        except Exception as e:
            logger.warning(f"Failed to update last boot timestamp: {e}")
    
    def _create_directory_structure(self) -> None:
        """Create Helios directory structure."""
        directories = [
            self.helios_dir,
            self.config.base_path,
            self.config.personas_path,
            self.config.learned_path,
            self.config.temporary_path
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {directory}")
    
    def _initialize_git_repo(self) -> None:
        """Initialize git repository in helios directory."""
        git_dir = self.helios_dir / ".git"
        if git_dir.exists():
            logger.debug("Git repository already exists")
            return
        
        try:
            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=self.helios_dir,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Create .gitignore
            gitignore_content = """# Temporary files
*.tmp
*.temp
*.lock

# Backup files
*.bak
*.backup

# System files
.DS_Store
Thumbs.db

# IDE files
.vscode/
.idea/
"""
            gitignore_path = self.helios_dir / ".gitignore"
            gitignore_path.write_text(gitignore_content, encoding='utf-8')
            
            # Set git config if not already set globally
            try:
                subprocess.run(["git", "config", "user.email"], 
                             cwd=self.helios_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # Set local config if global not set
                subprocess.run(
                    ["git", "config", "user.email", "helios@localhost"],
                    cwd=self.helios_dir, check=True
                )
                subprocess.run(
                    ["git", "config", "user.name", "Helios MCP"],
                    cwd=self.helios_dir, check=True
                )
            
            logger.debug("Initialized git repository")
            
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Failed to initialize git repository: {e}")
            # Git initialization is optional - don't fail bootstrap
    
    def _create_default_base_config(self) -> None:
        """Create default base identity configuration."""
        identity_file = self.config.base_path / "identity.yaml"
        
        if identity_file.exists() and validate_yaml_file(identity_file):
            logger.debug("Base identity configuration already exists")
            return
        
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
        
        atomic_write_yaml(identity_file, default_config)
        logger.info("Created default base identity configuration")
    
    def _create_welcome_persona(self) -> None:
        """Create a welcome persona for first-time users."""
        welcome_file = self.config.personas_path / "welcome.yaml"
        
        if welcome_file.exists() and validate_yaml_file(welcome_file):
            logger.debug("Welcome persona already exists")
            return
        
        welcome_config = {
            "name": "welcome",
            "base_importance": 0.8,
            "specialization_level": 1,
            "description": "Welcoming persona for new Helios users",
            "behaviors": {
                "communication": {
                    "tone": "Friendly and helpful",
                    "greeting": "Welcome to Helios! I'm here to help you get started.",
                    "style": "Patient and encouraging"
                },
                "guidance": {
                    "approach": "Start with basics, build complexity gradually",
                    "examples": "Provide clear, working examples",
                    "encouragement": "Acknowledge progress and celebrate successes"
                }
            },
            "created": datetime.datetime.now().strftime("%Y-%m-%d"),
            "version": "1.0.0"
        }
        
        atomic_write_yaml(welcome_file, welcome_config)
        logger.info("Created welcome persona")
    
    def _create_version_file(self) -> None:
        """Create version file marking successful installation."""
        version_data = {
            "version": "0.1.0",
            "install_date": datetime.datetime.now().isoformat(),
            "last_boot": datetime.datetime.now().isoformat(),
            "bootstrap_complete": True
        }
        
        atomic_write_yaml(self.version_file, version_data)
        logger.debug("Created version file")
    
    def _cleanup_failed_bootstrap(self) -> None:
        """Clean up after failed bootstrap attempt."""
        try:
            if self.version_file.exists():
                self.version_file.unlink()
            logger.debug("Cleaned up failed bootstrap")
        except Exception as e:
            logger.warning(f"Failed to clean up bootstrap: {e}")
