"""Atomic file operations for safe YAML handling."""

import os
import tempfile
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def atomic_write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Write YAML atomically to prevent corruption on crash.
    
    Uses a temporary file in the same directory to ensure atomic rename
    operation on POSIX and Windows systems. The temporary file is created
    with a .tmp suffix and renamed to the target path only after successful
    write.
    
    Args:
        path: Path to target YAML file
        data: Data to write as YAML
        
    Raises:
        OSError: If file operations fail
        yaml.YAMLError: If YAML serialization fails
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temporary file in same directory for atomic rename
    temp_fd = None
    temp_path = None
    
    try:
        # Create temporary file with .tmp suffix in target directory
        temp_fd, temp_name = tempfile.mkstemp(
            suffix='.tmp',
            prefix=f'{path.name}.',
            dir=path.parent,
            text=True
        )
        temp_path = Path(temp_name)
        
        # Write YAML data to temporary file
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            temp_fd = None  # File descriptor now owned by file object
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            # Ensure data is written to disk before rename
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic rename - this is the critical operation that makes it atomic
        # On POSIX systems, this is guaranteed atomic
        # On Windows, this works for files (but not directories)
        temp_path.replace(path)
        logger.debug(f"Atomically wrote YAML to {path}")
        
    except Exception as e:
        logger.error(f"Failed to write YAML atomically to {path}: {e}")
        # Clean up temporary file if it exists
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.warning(f"Failed to clean up temporary file {temp_path}")
        raise


def validate_yaml_file(path: Path) -> bool:
    """Validate that a YAML file is readable and parseable.
    
    Args:
        path: Path to YAML file to validate
        
    Returns:
        True if file is valid YAML, False otherwise
    """
    if not path.exists():
        return False
    
    try:
        with path.open('r', encoding='utf-8') as f:
            yaml.safe_load(f)
        return True
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return False


def backup_file(path: Path, suffix: str = '.bak') -> Path:
    """Create a backup copy of a file.
    
    Args:
        path: Path to file to backup
        suffix: Suffix to add to backup file
        
    Returns:
        Path to backup file
        
    Raises:
        OSError: If backup operation fails
    """
    if not path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {path}")
    
    backup_path = path.with_suffix(path.suffix + suffix)
    
    # If backup already exists, add timestamp
    if backup_path.exists():
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".{timestamp}{suffix}")
    
    # Use atomic operation for backup too
    import shutil
    shutil.copy2(path, backup_path)
    logger.debug(f"Created backup: {backup_path}")
    
    return backup_path
