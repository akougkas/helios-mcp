"""Tests for atomic file operations."""

import pytest
import os
import tempfile
import yaml
import stat
from pathlib import Path
from unittest.mock import patch, mock_open

from helios_mcp.atomic_ops import atomic_write_yaml, validate_yaml_file, backup_file


class TestAtomicWriteYaml:
    """Test atomic YAML writing operations."""
    
    def test_atomic_write_yaml_success(self, tmp_path):
        """Test normal atomic write succeeds."""
        target_file = tmp_path / "test.yaml"
        test_data = {
            "key1": "value1",
            "nested": {
                "key2": "value2",
                "number": 42
            }
        }
        
        # Write should succeed
        atomic_write_yaml(target_file, test_data)
        
        # File should exist and contain correct data
        assert target_file.exists()
        with target_file.open() as f:
            loaded_data = yaml.safe_load(f)
        assert loaded_data == test_data
    
    def test_atomic_write_yaml_creates_parent_dirs(self, tmp_path):
        """Test that parent directories are created."""
        target_file = tmp_path / "deep" / "nested" / "path" / "test.yaml"
        test_data = {"test": "data"}
        
        # Parent directories don't exist initially
        assert not target_file.parent.exists()
        
        # Write should create parent directories
        atomic_write_yaml(target_file, test_data)
        
        assert target_file.exists()
        assert target_file.parent.exists()
    
    def test_atomic_write_yaml_temp_file_cleanup_on_error(self, tmp_path):
        """Test that temporary files are cleaned up on write failure."""
        target_file = tmp_path / "test.yaml"
        
        # Mock yaml.safe_dump to raise an exception after temp file creation
        with patch('helios_mcp.atomic_ops.yaml.safe_dump') as mock_dump:
            mock_dump.side_effect = yaml.YAMLError("Serialization failed")
            
            # Count temp files before and after
            temp_files_before = list(tmp_path.glob("*.tmp"))
            
            with pytest.raises(yaml.YAMLError):
                atomic_write_yaml(target_file, {"test": "data"})
            
            # Should not leave temp files behind
            temp_files_after = list(tmp_path.glob("*.tmp"))
            assert len(temp_files_after) == len(temp_files_before)
    
    def test_atomic_write_yaml_preserves_existing_permissions(self, tmp_path):
        """Test that file permissions are preserved when overwriting."""
        target_file = tmp_path / "test.yaml"
        test_data = {"test": "data"}
        
        # Create initial file with specific permissions
        target_file.write_text("initial: data")
        target_file.chmod(0o644)
        original_mode = target_file.stat().st_mode
        
        # Overwrite with atomic operation
        atomic_write_yaml(target_file, test_data)
        
        # Check that data was updated
        with target_file.open() as f:
            loaded_data = yaml.safe_load(f)
        assert loaded_data == test_data
        
        # Permissions might not be exactly preserved on all systems,
        # but file should remain readable/writable
        assert target_file.is_file()
        assert os.access(target_file, os.R_OK | os.W_OK)
    
    @patch('helios_mcp.atomic_ops.os.fsync')
    def test_atomic_write_yaml_calls_fsync(self, mock_fsync, tmp_path):
        """Test that fsync is called to ensure data is written to disk."""
        target_file = tmp_path / "test.yaml"
        test_data = {"test": "data"}
        
        atomic_write_yaml(target_file, test_data)
        
        # fsync should have been called
        mock_fsync.assert_called_once()
    
    def test_atomic_write_yaml_handles_complex_data(self, tmp_path):
        """Test atomic write with complex nested data structures."""
        target_file = tmp_path / "complex.yaml"
        test_data = {
            "lists": [1, 2, 3, "string", {"nested": "dict"}],
            "nested": {
                "deeply": {
                    "nested": {
                        "data": "value",
                        "number": 3.14159,
                        "boolean": True,
                        "none_value": None
                    }
                }
            },
            "unicode": "测试数据 🚀",
            "multiline": "line 1\nline 2\nline 3"
        }
        
        atomic_write_yaml(target_file, test_data)
        
        # Verify data round-trip
        with target_file.open() as f:
            loaded_data = yaml.safe_load(f)
        assert loaded_data == test_data


class TestValidateYamlFile:
    """Test YAML file validation."""
    
    def test_validate_yaml_file_valid(self, tmp_path):
        """Test validation of valid YAML file."""
        valid_file = tmp_path / "valid.yaml"
        valid_data = {
            "key": "value",
            "nested": {"number": 42}
        }
        
        with valid_file.open('w') as f:
            yaml.safe_dump(valid_data, f)
        
        assert validate_yaml_file(valid_file) is True
    
    def test_validate_yaml_file_invalid(self, tmp_path):
        """Test validation of invalid YAML file."""
        invalid_file = tmp_path / "invalid.yaml"
        
        # Write invalid YAML
        invalid_file.write_text("key: value\n  invalid: indentation\nkey: duplicate")
        
        assert validate_yaml_file(invalid_file) is False
    
    def test_validate_yaml_file_missing(self, tmp_path):
        """Test validation of non-existent file."""
        missing_file = tmp_path / "missing.yaml"
        
        assert validate_yaml_file(missing_file) is False
    
    def test_validate_yaml_file_empty(self, tmp_path):
        """Test validation of empty YAML file."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        
        assert validate_yaml_file(empty_file) is True
    
    def test_validate_yaml_file_corrupt_encoding(self, tmp_path):
        """Test validation handles encoding errors."""
        corrupt_file = tmp_path / "corrupt.yaml"
        
        # Write invalid UTF-8 bytes
        with corrupt_file.open('wb') as f:
            f.write(b"key: value\n\xff\xfe invalid bytes")
        
        assert validate_yaml_file(corrupt_file) is False
    
    def test_validate_yaml_file_permission_denied(self, tmp_path):
        """Test validation handles permission errors."""
        restricted_file = tmp_path / "restricted.yaml"
        restricted_file.write_text("key: value")
        
        # Remove read permissions
        try:
            restricted_file.chmod(0o000)
            assert validate_yaml_file(restricted_file) is False
        finally:
            # Restore permissions for cleanup
            restricted_file.chmod(0o644)


class TestBackupFile:
    """Test file backup operations."""
    
    def test_backup_file_creation(self, tmp_path):
        """Test basic backup file creation."""
        source_file = tmp_path / "source.yaml"
        source_data = "test: data\nmore: content"
        source_file.write_text(source_data)
        
        backup_path = backup_file(source_file)
        
        # Backup should exist with .bak suffix
        expected_backup = source_file.with_suffix(source_file.suffix + ".bak")
        assert backup_path == expected_backup
        assert backup_path.exists()
        
        # Backup should have same content
        assert backup_path.read_text() == source_data
    
    def test_backup_file_custom_suffix(self, tmp_path):
        """Test backup with custom suffix."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        
        backup_path = backup_file(source_file, suffix=".backup")
        
        expected_backup = source_file.with_suffix(source_file.suffix + ".backup")
        assert backup_path == expected_backup
        assert backup_path.exists()
    
    def test_backup_file_timestamp_on_conflict(self, tmp_path):
        """Test that timestamp is added when backup already exists."""
        source_file = tmp_path / "source.yaml"
        source_file.write_text("original content")
        
        # Create first backup
        first_backup = backup_file(source_file)
        assert first_backup.exists()
        
        # Modify source and create second backup
        source_file.write_text("modified content")
        second_backup = backup_file(source_file)
        
        # Second backup should have timestamp in name
        assert second_backup != first_backup
        assert ".bak" in second_backup.name
        assert second_backup.exists()
        
        # Both backups should exist
        assert first_backup.exists()
        assert second_backup.read_text() == "modified content"
    
    def test_backup_file_preserves_metadata(self, tmp_path):
        """Test that file metadata is preserved in backup."""
        source_file = tmp_path / "source.yaml"
        source_file.write_text("test content")
        
        # Set specific modification time
        import time
        test_time = time.time() - 3600  # 1 hour ago
        os.utime(source_file, (test_time, test_time))
        original_stat = source_file.stat()
        
        backup_path = backup_file(source_file)
        backup_stat = backup_path.stat()
        
        # Modification time should be preserved (within tolerance)
        assert abs(backup_stat.st_mtime - original_stat.st_mtime) < 1
        assert backup_stat.st_size == original_stat.st_size
    
    def test_backup_file_nonexistent_source(self, tmp_path):
        """Test backup of non-existent file raises error."""
        missing_file = tmp_path / "missing.yaml"
        
        with pytest.raises(FileNotFoundError, match="Cannot backup non-existent file"):
            backup_file(missing_file)
    
    def test_backup_file_handles_long_names(self, tmp_path):
        """Test backup with very long filenames."""
        # Create file with long name
        long_name = "a" * 200 + ".yaml"
        source_file = tmp_path / long_name
        source_file.write_text("test content")
        
        # Backup should succeed even with long names
        backup_path = backup_file(source_file)
        assert backup_path.exists()
        assert backup_path.name.endswith(".bak")
    
    def test_backup_file_with_multiple_extensions(self, tmp_path):
        """Test backup with files having multiple extensions."""
        source_file = tmp_path / "config.backup.yaml"
        source_file.write_text("test: content")
        
        backup_path = backup_file(source_file, suffix=".old")
        
        # Should append to the final extension
        expected = tmp_path / "config.backup.yaml.old"
        assert backup_path == expected
        assert backup_path.exists()


class TestAtomicOpsIntegration:
    """Integration tests combining atomic operations."""
    
    def test_atomic_write_then_validate(self, tmp_path):
        """Test atomic write followed by validation."""
        target_file = tmp_path / "test.yaml"
        test_data = {"integration": "test", "number": 123}
        
        # Write atomically
        atomic_write_yaml(target_file, test_data)
        
        # Should validate successfully
        assert validate_yaml_file(target_file) is True
        
        # Should be readable
        with target_file.open() as f:
            loaded = yaml.safe_load(f)
        assert loaded == test_data
    
    def test_backup_before_atomic_write(self, tmp_path):
        """Test creating backup before atomic update."""
        target_file = tmp_path / "config.yaml"
        
        # Create initial file
        initial_data = {"version": "1.0", "setting": "old_value"}
        atomic_write_yaml(target_file, initial_data)
        
        # Create backup before update
        backup_path = backup_file(target_file)
        
        # Update atomically
        updated_data = {"version": "1.1", "setting": "new_value"}
        atomic_write_yaml(target_file, updated_data)
        
        # Both files should exist with correct content
        assert target_file.exists()
        assert backup_path.exists()
        
        with target_file.open() as f:
            current_data = yaml.safe_load(f)
        assert current_data == updated_data
        
        with backup_path.open() as f:
            backup_data = yaml.safe_load(f)
        assert backup_data == initial_data
    
    def test_error_recovery_workflow(self, tmp_path):
        """Test error recovery using backup files."""
        config_file = tmp_path / "critical_config.yaml"
        
        # Create working config
        good_data = {"database": {"host": "localhost", "port": 5432}}
        atomic_write_yaml(config_file, good_data)
        
        # Create backup before risky operation
        backup_path = backup_file(config_file)
        
        # Simulate failed update by writing invalid YAML manually
        config_file.write_text("invalid: yaml: content: [")
        
        # Validation should fail
        assert validate_yaml_file(config_file) is False
        
        # Restore from backup
        import shutil
        shutil.copy2(backup_path, config_file)
        
        # Should now be valid again
        assert validate_yaml_file(config_file) is True
        
        with config_file.open() as f:
            restored_data = yaml.safe_load(f)
        assert restored_data == good_data