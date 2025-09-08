"""Atomic file operations for safe YAML handling with resource management."""

import os
import tempfile
import yaml
import logging
import contextlib
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import time

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manages system resources for atomic operations."""
    
    def __init__(self, max_concurrent_ops: int = 10, max_temp_files: int = 100):
        self.max_concurrent_ops = max_concurrent_ops
        self.max_temp_files = max_temp_files
        self._semaphore = threading.Semaphore(max_concurrent_ops)
        self._temp_files = set()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_ops, thread_name_prefix="atomic-ops")
    
    @contextlib.contextmanager
    def acquire_operation_slot(self):
        """Context manager for limiting concurrent operations."""
        acquired = self._semaphore.acquire(timeout=30.0)  # 30 second timeout
        if not acquired:
            raise RuntimeError("Failed to acquire operation slot within timeout")
        try:
            yield
        finally:
            self._semaphore.release()
    
    def register_temp_file(self, path: Path) -> None:
        """Register a temporary file for cleanup tracking."""
        with self._lock:
            if len(self._temp_files) >= self.max_temp_files:
                # Clean up some old temp files
                self._cleanup_stale_temp_files()
            self._temp_files.add(path)
    
    def unregister_temp_file(self, path: Path) -> None:
        """Unregister a temporary file."""
        with self._lock:
            self._temp_files.discard(path)
    
    def _cleanup_stale_temp_files(self) -> None:
        """Clean up stale temporary files."""
        current_time = time.time()
        to_remove = []
        
        for temp_path in list(self._temp_files):
            try:
                if not temp_path.exists():
                    to_remove.append(temp_path)
                elif current_time - temp_path.stat().st_mtime > 3600:  # 1 hour old
                    temp_path.unlink()
                    to_remove.append(temp_path)
                    logger.debug(f"Cleaned up stale temp file: {temp_path}")
            except (OSError, AttributeError):
                to_remove.append(temp_path)
        
        for path in to_remove:
            self._temp_files.discard(path)
    
    def cleanup_all(self) -> None:
        """Clean up all tracked resources."""
        with self._lock:
            for temp_path in list(self._temp_files):
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass
            self._temp_files.clear()
        
        self._executor.shutdown(wait=True)


# Global resource manager
_resource_manager: Optional[ResourceManager] = None


def get_resource_manager() -> ResourceManager:
    """Get global resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = ResourceManager()
    return _resource_manager


@contextlib.contextmanager
def atomic_file_operation(path: Path, mode: str = 'w'):
    """Context manager for atomic file operations with proper resource management.
    
    Args:
        path: Target file path
        mode: File open mode
        
    Yields:
        Tuple of (temp_file_handle, temp_path)
    """
    resource_manager = get_resource_manager()
    
    with resource_manager.acquire_operation_slot():
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create temporary file with proper cleanup
        temp_fd = None
        temp_path = None
        
        try:
            # Create temporary file with .tmp suffix in target directory
            temp_fd, temp_name = tempfile.mkstemp(
                suffix='.tmp',
                prefix=f'{path.name}.',
                dir=path.parent,
                text='b' not in mode
            )
            temp_path = Path(temp_name)
            resource_manager.register_temp_file(temp_path)
            
            # Yield file handle for writing
            with os.fdopen(temp_fd, mode, encoding='utf-8' if 'b' not in mode else None) as f:
                temp_fd = None  # File descriptor now owned by file object
                yield f, temp_path
                
                # Ensure data is written to disk before rename
                f.flush()
                if hasattr(f, 'fileno'):
                    os.fsync(f.fileno())
            
            # Atomic rename - this is the critical operation that makes it atomic
            temp_path.replace(path)
            logger.debug(f"Atomically wrote to {path}")
            
        except Exception:
            # Clean up temporary file on error
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    logger.warning(f"Failed to clean up temporary file {temp_path}")
            raise
        finally:
            # Ensure file descriptor is closed if still open
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            
            # Unregister temp file
            if temp_path:
                resource_manager.unregister_temp_file(temp_path)


def atomic_write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Write YAML atomically with improved resource management.
    
    Uses context managers and resource limits to prevent file descriptor leaks
    and resource exhaustion.
    
    Args:
        path: Path to target YAML file
        data: Data to write as YAML
        
    Raises:
        OSError: If file operations fail
        yaml.YAMLError: If YAML serialization fails
        RuntimeError: If resource limits are exceeded
    """
    try:
        with atomic_file_operation(path, 'w') as (f, temp_path):
            yaml.safe_dump(
                data, 
                f, 
                default_flow_style=False, 
                sort_keys=False,
                allow_unicode=True,
                encoding=None  # Let the file handle manage encoding
            )
        logger.debug(f"Atomically wrote YAML to {path}")
    except Exception as e:
        logger.error(f"Failed to write YAML atomically to {path}: {e}")
        raise


def validate_yaml_file(path: Path, max_file_size_mb: float = 10.0) -> bool:
    """Validate that a YAML file is readable and parseable with size limits.
    
    Args:
        path: Path to YAML file to validate
        max_file_size_mb: Maximum allowed file size in MB
        
    Returns:
        True if file is valid YAML, False otherwise
    """
    if not path.exists():
        return False
    
    try:
        # Check file size to prevent memory exhaustion
        file_size = path.stat().st_size
        if file_size > max_file_size_mb * 1024 * 1024:
            logger.warning(f"YAML file {path} too large ({file_size / 1024 / 1024:.1f}MB > {max_file_size_mb}MB)")
            return False
        
        # Use context manager for proper resource cleanup
        with path.open('r', encoding='utf-8') as f:
            yaml.safe_load(f)
        return True
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
        logger.debug(f"YAML validation failed for {path}: {e}")
        return False


def backup_file(path: Path, suffix: str = '.bak', max_backups: int = 5) -> Path:
    """Create a backup copy of a file with automatic cleanup of old backups.
    
    Args:
        path: Path to file to backup
        suffix: Suffix to add to backup file
        max_backups: Maximum number of backup files to keep
        
    Returns:
        Path to backup file
        
    Raises:
        OSError: If backup operation fails
        FileNotFoundError: If source file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {path}")
    
    backup_path = path.with_suffix(path.suffix + suffix)
    
    # If backup already exists, add timestamp
    if backup_path.exists():
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".{timestamp}{suffix}")
    
    try:
        # Use atomic operation for backup too
        with atomic_file_operation(backup_path, 'wb') as (dest_f, _):
            with path.open('rb') as src_f:
                # Copy in chunks to avoid memory issues with large files
                chunk_size = 64 * 1024  # 64KB chunks
                while True:
                    chunk = src_f.read(chunk_size)
                    if not chunk:
                        break
                    dest_f.write(chunk)
        
        logger.debug(f"Created backup: {backup_path}")
        
        # Clean up old backups
        _cleanup_old_backups(path, suffix, max_backups)
        
        return backup_path
        
    except Exception as e:
        logger.error(f"Failed to create backup of {path}: {e}")
        raise


def _cleanup_old_backups(original_path: Path, suffix: str, max_backups: int) -> None:
    """Clean up old backup files to prevent disk space exhaustion.
    
    Args:
        original_path: Original file path
        suffix: Backup file suffix
        max_backups: Maximum number of backups to keep
    """
    try:
        # Find all backup files for this original file
        backup_pattern = f"{original_path.stem}*{suffix}"
        backup_files = list(original_path.parent.glob(backup_pattern))
        
        if len(backup_files) <= max_backups:
            return
        
        # Sort by modification time, oldest first
        backup_files.sort(key=lambda p: p.stat().st_mtime)
        
        # Remove oldest backups
        files_to_remove = backup_files[:len(backup_files) - max_backups]
        for backup_file in files_to_remove:
            try:
                backup_file.unlink()
                logger.debug(f"Removed old backup: {backup_file}")
            except OSError as e:
                logger.warning(f"Failed to remove old backup {backup_file}: {e}")
                
    except Exception as e:
        logger.warning(f"Failed to cleanup old backups for {original_path}: {e}")


def cleanup_resources() -> None:
    """Clean up all atomic operation resources."""
    global _resource_manager
    if _resource_manager:
        _resource_manager.cleanup_all()
        _resource_manager = None
