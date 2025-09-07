"""Git persistence for Helios behavioral configurations.

Provides git-based versioning of YAML configurations with automated
commit messages and repository management.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

from git import Repo, InvalidGitRepositoryError
import logging

logger = logging.getLogger(__name__)


class GitStore:
    """Git-based persistence for Helios configuration files.
    
    Manages ~/.helios as a git repository with automated commits
    for configuration changes and behavioral evolution.
    """
    
    def __init__(self, helios_dir: Optional[Path] = None):
        """Initialize git store.
        
        Args:
            helios_dir: Directory for Helios configs. Defaults to ~/.helios
        """
        self.helios_dir = helios_dir or Path.home() / '.helios'
        self.repo = self.get_or_create_repo()
    
    def get_or_create_repo(self) -> Repo:
        """Initialize ~/.helios as git repo if needed.
        
        Returns:
            Git repository instance
            
        Raises:
            Exception: If git initialization fails
        """
        try:
            # Try to open existing repository
            repo = Repo(str(self.helios_dir))
            logger.debug(f"Found existing git repo at {self.helios_dir}")
            return repo
        except InvalidGitRepositoryError:
            # Directory exists but is not a git repository
            logger.info(f"Initializing git repo at {self.helios_dir}")
            return Repo.init(str(self.helios_dir))
        except FileNotFoundError:
            # Directory doesn't exist, create it and initialize repo
            os.makedirs(self.helios_dir, exist_ok=True)
            logger.info(f"Creating directory and git repo at {self.helios_dir}")
            return Repo.init(str(self.helios_dir))
    
    def auto_commit(self, change_type: str = "config", persona: Optional[str] = None, 
                   file_type: Optional[str] = None) -> bool:
        """Auto-commit any YAML configuration changes.
        
        Args:
            change_type: Type of change (persona_update, base_update, learning, etc.)
            persona: Specific persona being modified
            file_type: Type of configuration file
            
        Returns:
            True if changes were committed, False if repo was clean
        """
        try:
            # Check if there are any changes to commit
            if not self.repo.is_dirty() and not self.repo.untracked_files:
                logger.debug("Repository is clean, no changes to commit")
                return False
            
            # Add all changed files (including untracked)
            self.repo.git.add(A=True)  # Equivalent to 'git add -A'
            
            # Generate descriptive commit message
            message = self._generate_commit_message(change_type, persona, file_type)
            
            # Create commit
            self.repo.index.commit(message)
            logger.info(f"Committed changes: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            return False
    
    def commit_file_change(self, file_path: Path, change_type: str, 
                          persona: Optional[str] = None) -> bool:
        """Commit specific file with descriptive message.
        
        Args:
            file_path: Path to the changed file
            change_type: Type of change being made
            persona: Related persona if applicable
            
        Returns:
            True if file was committed, False otherwise
        """
        try:
            rel_path = str(file_path.relative_to(self.helios_dir))
            
            if not self.repo.is_dirty(path=rel_path):
                logger.debug(f"No changes to commit for {rel_path}")
                return False
                
            # Add specific file
            self.repo.index.add([rel_path])
            
            # Generate commit message
            message = self._generate_commit_message(change_type, persona, rel_path)
            
            # Commit the change
            self.repo.index.commit(message)
            logger.info(f"Committed file change: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to commit file {file_path}: {e}")
            return False
    
    def has_uncommitted_changes(self, file_path: Optional[Path] = None) -> bool:
        """Check if repository or specific file has uncommitted changes.
        
        Args:
            file_path: Specific file to check, or None for entire repo
            
        Returns:
            True if there are uncommitted changes
        """
        try:
            if file_path:
                rel_path = str(file_path.relative_to(self.helios_dir))
                return self.repo.is_dirty(path=rel_path)
            return self.repo.is_dirty() or bool(self.repo.untracked_files)
        except Exception as e:
            logger.error(f"Error checking repository status: {e}")
            return False
    
    def get_repo_status(self) -> Dict[str, Any]:
        """Get comprehensive repository status.
        
        Returns:
            Dictionary with repository status information
        """
        try:
            return {
                'is_dirty': self.repo.is_dirty(),
                'untracked_files': self.repo.untracked_files,
                'modified_files': [item.a_path for item in self.repo.index.diff(None)],
                'staged_files': [item.a_path for item in self.repo.index.diff("HEAD")] if self.repo.heads else [],
                'clean': not self.repo.is_dirty() and not self.repo.untracked_files
            }
        except Exception as e:
            logger.error(f"Error getting repository status: {e}")
            return {
                'is_dirty': False,
                'untracked_files': [],
                'modified_files': [],
                'staged_files': [],
                'clean': True,
                'error': str(e)
            }
    
    def get_config_history(self, config_file: Path, limit: int = 10) -> List[Dict[str, Any]]:
        """Get evolution history of specific configuration file.
        
        Args:
            config_file: Path to configuration file
            limit: Maximum number of commits to return
            
        Returns:
            List of commit information dictionaries
        """
        try:
            rel_path = str(config_file.relative_to(self.helios_dir))
            commits = list(self.repo.iter_commits(paths=rel_path, max_count=limit))
            
            return [{
                'hash': commit.hexsha[:8],
                'message': commit.message.strip(),
                'author': str(commit.author),
                'date': commit.committed_datetime.isoformat(),
                'files_changed': list(commit.stats.files.keys())
            } for commit in commits]
            
        except Exception as e:
            logger.error(f"Error getting config history for {config_file}: {e}")
            return []
    
    def get_recent_changes(self, hours: int = 24) -> List[str]:
        """Get commits from last N hours for behavior tracking.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of recent commit messages
        """
        try:
            if not self.repo.heads:  # No commits yet
                return []
                
            since = self.repo.head.commit.committed_datetime - timedelta(hours=hours)
            commits = list(self.repo.iter_commits(since=since))
            
            return [commit.message.strip() for commit in commits]
            
        except Exception as e:
            logger.error(f"Error getting recent changes: {e}")
            return []
    
    def _generate_commit_message(self, change_type: str, persona: Optional[str] = None, 
                                file_type: Optional[str] = None) -> str:
        """Generate descriptive commit messages for behavior changes.
        
        Args:
            change_type: Type of change being made
            persona: Specific persona if applicable
            file_type: Type of configuration file
            
        Returns:
            Formatted commit message
        """
        # Conventional commit format for configuration changes
        templates = {
            'persona_update': f"config(persona): update {persona} behavioral settings",
            'base_update': "config(base): update core behavioral configuration", 
            'learning': f"learn: incorporate new behavioral pattern for {persona}",
            'inheritance': f"config(inheritance): adjust weight calculation for {persona}",
            'initialization': "feat: initialize Helios behavioral configuration",
            'yaml_update': f"config: update {file_type} configuration",
            'preference': f"config(preference): update {persona} preferences" if persona else "config(preference): update preferences",
            'pattern': f"learn: record behavioral pattern for {persona}" if persona else "learn: record behavioral pattern",
        }
        
        message = templates.get(change_type)
        if message:
            return message
            
        # Fallback for unknown change types
        if persona and file_type:
            return f"config({persona}): update {file_type}"
        elif persona:
            return f"config({persona}): {change_type}"
        elif file_type:
            return f"config: update {file_type} - {change_type}"
        else:
            return f"config: {change_type}"
    
    def safe_operation(self, operation_func, *args, **kwargs):
        """Safely execute git operations with error handling.
        
        Args:
            operation_func: Function to execute safely
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of operation or None if it fails
        """
        try:
            return operation_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Git operation failed: {e}")
            return None
