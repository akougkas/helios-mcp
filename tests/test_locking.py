"""Tests for process locking functionality."""

import pytest
import os
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from helios_mcp.locking import ProcessLock


class TestProcessLock:
    """Test process locking mechanisms."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for lock files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def lock(self, temp_dir):
        """Create ProcessLock instance."""
        return ProcessLock(temp_dir)
    
    def test_acquire_lock_success(self, lock, temp_dir):
        """Test successful lock acquisition."""
        assert lock.acquire() is True
        assert (temp_dir / ".helios.lock").exists()
        lock.release()
    
    def test_acquire_lock_already_locked(self, temp_dir):
        """Test lock acquisition when already locked."""
        lock1 = ProcessLock(temp_dir)
        lock2 = ProcessLock(temp_dir)
        
        assert lock1.acquire() is True
        assert lock2.acquire() is False
        
        lock1.release()
    
    def test_release_lock(self, lock, temp_dir):
        """Test lock release."""
        lock.acquire()
        lock.release()
        assert not (temp_dir / ".helios.lock").exists()
    
    def test_is_locked(self, lock):
        """Test lock status checking."""
        assert lock.is_locked() is False
        lock.acquire()
        assert lock.is_locked() is True
        lock.release()
        assert lock.is_locked() is False
    
    @patch('helios_mcp.locking.psutil.pid_exists')
    def test_cleanup_stale_lock(self, mock_pid_exists, temp_dir):
        """Test stale lock cleanup."""
        lock = ProcessLock(temp_dir)
        lock_file = temp_dir / ".helios.lock"
        
        # Create stale lock (old timestamp, dead process)
        lock_data = {"pid": 99999, "timestamp": time.time() - 600}  # 10 mins ago
        lock_file.write_text(json.dumps(lock_data))
        mock_pid_exists.return_value = False
        
        # Should clean up stale lock and acquire
        assert lock.acquire() is True
        lock.release()
    
    @patch('helios_mcp.locking.psutil.pid_exists')
    def test_active_lock_not_cleaned(self, mock_pid_exists, temp_dir):
        """Test that active locks are not cleaned."""
        lock = ProcessLock(temp_dir)
        lock_file = temp_dir / ".helios.lock"
        
        # Create recent lock with different PID (not our process)
        different_pid = 99999
        lock_data = {"pid": different_pid, "timestamp": time.time()}
        lock_file.write_text(json.dumps(lock_data))
        mock_pid_exists.return_value = True
        
        # Should not clean active lock
        assert lock.acquire() is False
    
    def test_context_manager(self, temp_dir):
        """Test context manager usage."""
        lock = ProcessLock(temp_dir)
        
        with lock:
            assert (temp_dir / ".helios.lock").exists()
        
        assert not (temp_dir / ".helios.lock").exists()
    
    def test_context_manager_exception(self, temp_dir):
        """Test context manager releases lock on exception."""
        lock = ProcessLock(temp_dir)
        
        with pytest.raises(ValueError):
            with lock:
                assert (temp_dir / ".helios.lock").exists()
                raise ValueError("Test error")
        
        assert not (temp_dir / ".helios.lock").exists()
    
    def test_cleanup_stale_removes_old_locks(self, temp_dir):
        """Test cleanup_stale removes only old locks."""
        lock = ProcessLock(temp_dir)
        lock_file = temp_dir / ".helios.lock"
        
        # Create stale lock
        lock_data = {"pid": 99999, "timestamp": time.time() - 600}  # 10 mins ago
        lock_file.write_text(json.dumps(lock_data))
        
        lock.cleanup_stale()
        assert not lock_file.exists()
    
    def test_lock_file_corruption_handled(self, temp_dir):
        """Test handling of corrupted lock files."""
        lock = ProcessLock(temp_dir)
        lock_file = temp_dir / ".helios.lock"
        
        # Create corrupted lock file
        lock_file.write_text("corrupted data")
        
        # Should handle corruption and acquire lock
        assert lock.acquire() is True
        lock.release()