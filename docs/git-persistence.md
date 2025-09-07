# GitPython - Git Persistence Patterns
**Updated**: 2025-09-07
**Version**: GitPython 3.1.45
**Source**: Official docs + Stack Overflow patterns

## Quick Reference
```python
from git import Repo, InvalidGitRepositoryError
import os

# Initialize or get existing repo
repo = get_or_create_repo(path)

# Check for changes
if repo.is_dirty() or repo.untracked_files:
    # Auto-commit changes
    auto_commit_changes(repo, "behavior: update persona settings")
```

## Core Patterns for Helios

### 1. Repository Initialization/Check
```python
from git import Repo, InvalidGitRepositoryError

def get_or_create_repo(path: str) -> Repo:
    """
    Get existing repo or create new one if it doesn't exist.
    Safe to run multiple times - git init won't overwrite existing repos.
    """
    try:
        # Try to open existing repository
        repo = Repo(path)
        return repo
    except InvalidGitRepositoryError:
        # Directory exists but is not a git repository
        return Repo.init(path)
    except FileNotFoundError:
        # Directory doesn't exist, create it and initialize repo
        os.makedirs(path, exist_ok=True)
        return Repo.init(path)

def is_git_repo(path: str) -> bool:
    """Check if directory is a git repository."""
    try:
        _ = Repo(path).git_dir
        return True
    except InvalidGitRepositoryError:
        return False
```

### 2. Auto-Commit YAML Changes
```python
def auto_commit_changes(repo: Repo, message: str) -> bool:
    """
    Lightweight commit pattern for configuration changes.
    Returns True if changes were committed, False if repo was clean.
    """
    # Check if there are any changes to commit
    if not repo.is_dirty() and not repo.untracked_files:
        return False
    
    # Add all changed files (including untracked)
    repo.git.add(A=True)  # Equivalent to 'git add -A'
    
    # Create commit with descriptive message
    repo.index.commit(message)
    return True

def commit_yaml_change(repo: Repo, file_path: str, change_type: str) -> None:
    """Commit specific YAML file with descriptive message."""
    if repo.is_dirty(path=file_path):
        repo.index.add([file_path])
        
        # Generate descriptive commit message
        rel_path = os.path.relpath(file_path, repo.working_dir)
        message = f"{change_type}: update {rel_path}"
        
        repo.index.commit(message)
```

### 3. Checking Uncommitted Changes
```python
def check_repo_status(repo: Repo) -> dict:
    """Get comprehensive repository status."""
    return {
        'is_dirty': repo.is_dirty(),
        'untracked_files': repo.untracked_files,
        'modified_files': [item.a_path for item in repo.index.diff(None)],
        'staged_files': [item.a_path for item in repo.index.diff("HEAD")],
        'clean': not repo.is_dirty() and not repo.untracked_files
    }

def has_uncommitted_changes(repo: Repo, file_path: str = None) -> bool:
    """Check if specific file or entire repo has uncommitted changes."""
    if file_path:
        return repo.is_dirty(path=file_path)
    return repo.is_dirty() or bool(repo.untracked_files)
```

### 4. Helios-Specific Commit Messages
```python
def generate_commit_message(change_type: str, persona: str = None, 
                          file_type: str = None) -> str:
    """Generate descriptive commit messages for behavior changes."""
    
    # Conventional commit format for configuration changes
    templates = {
        'persona_update': f"config(persona): update {persona} behavioral settings",
        'base_update': "config(base): update core behavioral configuration", 
        'learning': f"learn: incorporate new behavioral pattern for {persona}",
        'inheritance': f"config(inheritance): adjust weight calculation for {persona}",
        'initialization': "feat: initialize Helios behavioral configuration",
        'yaml_update': f"config: update {file_type} configuration"
    }
    
    return templates.get(change_type, f"config: {change_type}")

# Usage examples
commit_message = generate_commit_message('persona_update', 'research-assistant')
commit_message = generate_commit_message('learning', 'code-reviewer')
```

### 5. Lightweight Git History Tracking
```python
def get_behavior_evolution(repo: Repo, file_path: str, limit: int = 10) -> list:
    """Track evolution of specific configuration file through git history."""
    commits = list(repo.iter_commits(paths=file_path, max_count=limit))
    
    return [{
        'hash': commit.hexsha[:8],
        'message': commit.message.strip(),
        'author': str(commit.author),
        'date': commit.committed_datetime.isoformat(),
        'files_changed': list(commit.stats.files.keys())
    } for commit in commits]

def get_recent_changes(repo: Repo, hours: int = 24) -> list:
    """Get commits from last N hours for behavior tracking."""
    since = repo.head.commit.committed_datetime - timedelta(hours=hours)
    commits = list(repo.iter_commits(since=since))
    
    return [commit.message.strip() for commit in commits]
```

## Complete Helios Integration Example
```python
import os
from pathlib import Path
from git import Repo, InvalidGitRepositoryError

class GitPersistence:
    """Lightweight git persistence for Helios configuration."""
    
    def __init__(self, helios_dir: Path = None):
        self.helios_dir = helios_dir or Path.home() / '.helios'
        self.repo = self.get_or_create_repo(str(self.helios_dir))
    
    def get_or_create_repo(self, path: str) -> Repo:
        """Initialize ~/.helios as git repo if needed."""
        try:
            return Repo(path)
        except InvalidGitRepositoryError:
            return Repo.init(path)
        except FileNotFoundError:
            os.makedirs(path, exist_ok=True)
            return Repo.init(path)
    
    def save_config(self, file_path: str, change_type: str, persona: str = None):
        """Save configuration change with descriptive commit."""
        if not self.repo.is_dirty() and not self.repo.untracked_files:
            return False
        
        # Add all changes
        self.repo.git.add(A=True)
        
        # Generate commit message
        message = generate_commit_message(change_type, persona)
        
        # Commit changes
        self.repo.index.commit(message)
        return True
    
    def get_config_history(self, config_file: str, limit: int = 5):
        """Get recent changes to specific config file."""
        file_path = str(Path(config_file).relative_to(self.helios_dir))
        return get_behavior_evolution(self.repo, file_path, limit)
```

## Error Handling
```python
def safe_git_operation(operation_func, *args, **kwargs):
    """Safely execute git operations with error handling."""
    try:
        return operation_func(*args, **kwargs)
    except Exception as e:
        # Log error but don't break configuration management
        print(f"Git operation failed: {e}")
        return None

# Usage
result = safe_git_operation(auto_commit_changes, repo, "config: update persona")
```

## Performance Notes
- `repo.is_dirty()` is fast - it only checks git index vs working directory
- Use `repo.git.add(A=True)` instead of `repo.index.add()` for bulk operations
- Git operations are local filesystem only - no network overhead
- Small YAML files commit very quickly
- Git handles incremental changes efficiently

## Common Issues
- **Permission errors**: Ensure ~/.helios is writable
- **Empty commits**: Check `repo.is_dirty()` before committing
- **Large files**: YAML configs are small, not a concern for performance
- **Git not installed**: GitPython requires git binary in PATH

## Best Practices for Helios
1. **Commit frequently**: Every behavior change gets its own commit
2. **Descriptive messages**: Use conventional commit format
3. **Local only**: No remote repos needed, pure local persistence
4. **Graceful degradation**: Configuration works even if git fails
5. **Lightweight operations**: Fast enough for real-time config changes