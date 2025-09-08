"""Process locking for Helios MCP server.

Provides single-instance enforcement with stale lock cleanup.
Prevents multiple server instances from running simultaneously.
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Optional
import psutil

logger = logging.getLogger(__name__)


class ProcessLock:
    """Single-instance enforcement with stale lock cleanup.
    
    Features:
    - Write PID and timestamp to .helios.lock file
    - Clean stale locks (>5 minutes old)
    - Check if PID is actually running
    - Handle graceful release on exit
    - Work on both Linux and macOS
    """
    
    def __init__(self, helios_dir: Path, max_age_seconds: float = 300.0):
        """
        Args:
            helios_dir: Path to Helios configuration directory
            max_age_seconds: Max age before considering a lock stale (default: 5 minutes)
        """
        self.helios_dir = helios_dir
        self.lock_file = helios_dir / ".helios.lock"
        self.max_age_seconds = max_age_seconds
        self.current_pid = os.getpid()
        self.acquired = False
        
        # Ensure helios directory exists for lock file
        self.helios_dir.mkdir(parents=True, exist_ok=True)
    
    def acquire(self) -> bool:
        """Attempt to acquire the process lock.
        
        Returns:
            True if lock was acquired, False if another process holds it
        """
        if self.acquired:
            return True
            
        try:
            # Note: We no longer clean up stale locks proactively to avoid TOCTOU.
            # Cleanup only happens after O_EXCL fails, ensuring atomicity.
            
            # Create lock data
            lock_data = {
                "pid": self.current_pid,
                "timestamp": time.time(),
                "hostname": os.uname().nodename if hasattr(os, 'uname') else "unknown",
                "start_time": time.time()
            }
            
            # Use exclusive file creation with O_EXCL flag (atomic operation)
            # This eliminates the TOCTOU race condition by relying solely on O_EXCL atomicity
            try:
                # O_CREAT | O_EXCL fails if file exists (atomic operation)
                fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                try:
                    with os.fdopen(fd, 'w') as f:
                        json.dump(lock_data, f, indent=2)
                except Exception:
                    # If we fail to write, close the fd and remove the file
                    os.close(fd)
                    self._remove_lock_file()
                    raise
            except FileExistsError:
                # File exists - check if it's stale and clean up if needed
                self.cleanup_stale()
                
                # Try once more after cleanup
                try:
                    fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                    try:
                        with os.fdopen(fd, 'w') as f:
                            json.dump(lock_data, f, indent=2)
                    except Exception:
                        os.close(fd)
                        self._remove_lock_file()
                        raise
                except FileExistsError:
                    # Another process still holds the lock after cleanup
                    logger.info(f"Another Helios instance is already running (lock at {self.lock_file})")
                    return False
            
            self.acquired = True
            logger.info(f"Process lock acquired (PID: {self.current_pid})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to acquire process lock: {e}")
            return False
    
    def release(self) -> None:
        """Release the process lock."""
        if not self.acquired:
            return
            
        try:
            # Verify we still own the lock before removing it
            if self.lock_file.exists():
                lock_data = self._read_lock_data()
                if lock_data and lock_data.get("pid") == self.current_pid:
                    self._remove_lock_file()
                    logger.info(f"Process lock released (PID: {self.current_pid})")
                else:
                    logger.warning("Lock file appears to be owned by another process")
            
            self.acquired = False
            
        except Exception as e:
            logger.error(f"Error releasing process lock: {e}")
    
    def is_locked(self) -> bool:
        """Check if a valid lock exists.
        
        Returns:
            True if lock exists and is valid, False otherwise
        """
        if not self.lock_file.exists():
            return False
        
        return self._is_lock_valid()
    
    def cleanup_stale(self) -> None:
        """Remove stale lock files.
        
        This function is called after a FileExistsError to check if the existing
        lock file is stale and can be safely removed.
        """
        if not self.lock_file.exists():
            return
            
        try:
            lock_data = self._read_lock_data()
            if not lock_data:
                # Corrupt lock file, remove it
                logger.warning("Removing corrupt lock file")
                self._remove_lock_file()
                return
            
            # Don't remove our own lock
            if lock_data.get("pid") == self.current_pid:
                return
            
            # Check if lock is stale by age
            lock_age = time.time() - lock_data.get("timestamp", 0)
            if lock_age > self.max_age_seconds:
                logger.info(f"Removing stale lock file (age: {lock_age:.1f}s)")
                self._remove_lock_file()
                return
            
            # Check if the process is still running
            pid = lock_data.get("pid")
            if pid and not self._is_process_running(pid):
                logger.info(f"Removing lock for dead process (PID: {pid})")
                self._remove_lock_file()
                return
                
        except Exception as e:
            logger.error(f"Error during stale lock cleanup: {e}")
    
    def _is_lock_valid(self) -> bool:
        """Check if the current lock file is valid.
        
        Returns:
            True if lock is valid and process is running, False otherwise
        """
        try:
            lock_data = self._read_lock_data()
            if not lock_data:
                return False
            
            # Check if it's our own lock
            if lock_data.get("pid") == self.current_pid:
                return True
            
            # Check age
            lock_age = time.time() - lock_data.get("timestamp", 0)
            if lock_age > self.max_age_seconds:
                return False
            
            # Check if process is still running
            pid = lock_data.get("pid")
            if not pid or not self._is_process_running(pid):
                return False
            
            return True
            
        except Exception:
            return False
    
    def _read_lock_data(self) -> Optional[dict]:
        """Read lock file data.
        
        Returns:
            Lock data dictionary or None if invalid/corrupt
        """
        try:
            with self.lock_file.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            return None
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running.
        
        Args:
            pid: Process ID to check
            
        Returns:
            True if process is running, False otherwise
        """
        try:
            # Use psutil for cross-platform process checking
            return psutil.pid_exists(pid)
        except Exception:
            # Fallback to os.kill method on Unix-like systems
            try:
                os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
                return True
            except (OSError, ProcessLookupError):
                return False
    
    def _remove_lock_file(self) -> None:
        """Safely remove lock file.
        
        Only removes the file if we own it or if it's demonstrably stale.
        """
        try:
            if self.lock_file.exists():
                # Extra safety: check if we own this lock before removing
                try:
                    lock_data = self._read_lock_data()
                    if lock_data and lock_data.get("pid") != self.current_pid:
                        # Not our lock - only remove if process is dead
                        pid = lock_data.get("pid")
                        if pid and self._is_process_running(pid):
                            logger.warning(f"Not removing lock file owned by running process {pid}")
                            return
                except Exception:
                    # If we can't read lock data, it's probably corrupt, safe to remove
                    pass
                
                self.lock_file.unlink()
        except Exception as e:
            logger.error(f"Failed to remove lock file: {e}")
    
    def __enter__(self) -> "ProcessLock":
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError("Failed to acquire process lock")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.release()
