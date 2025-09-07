"""Tests for bootstrap and installation detection."""

import pytest
import subprocess
import yaml
import datetime
from pathlib import Path
from unittest.mock import Mock, patch, call

from helios_mcp.bootstrap import BootstrapManager
from helios_mcp.config import HeliosConfig


class TestBootstrapManager:
    """Test BootstrapManager initialization and basic functionality."""
    
    def test_bootstrap_manager_initialization(self, tmp_path):
        """Test BootstrapManager initialization."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        assert manager.helios_dir == helios_dir
        assert manager.version_file == helios_dir / ".helios_version"
        assert isinstance(manager.config, HeliosConfig)
        
        # Check config paths are set correctly
        assert manager.config.base_path == helios_dir / "base"
        assert manager.config.personas_path == helios_dir / "personas"
        assert manager.config.learned_path == helios_dir / "learned"
        assert manager.config.temporary_path == helios_dir / "temporary"


class TestFirstInstallDetection:
    """Test first installation detection logic."""
    
    def test_is_first_install_true(self, tmp_path):
        """Test detection of fresh installation."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Version file doesn't exist, should be first install
        assert manager.is_first_install() is True
    
    def test_is_first_install_false(self, tmp_path):
        """Test detection of existing installation."""
        helios_dir = tmp_path / ".helios"
        helios_dir.mkdir()
        
        # Create version file to simulate existing installation
        version_file = helios_dir / ".helios_version"
        version_file.write_text("version: 0.1.0")
        
        manager = BootstrapManager(helios_dir)
        assert manager.is_first_install() is False


class TestBootstrapInstallation:
    """Test the full bootstrap installation process."""
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_bootstrap_installation_creates_structure(self, mock_subprocess, tmp_path):
        """Test that bootstrap creates all necessary directories."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Mock git commands to succeed
        mock_subprocess.return_value = Mock(returncode=0)
        
        # Bootstrap should create all directories
        manager.bootstrap_installation()
        
        # All directories should exist
        assert helios_dir.exists()
        assert manager.config.base_path.exists()
        assert manager.config.personas_path.exists()
        assert manager.config.learned_path.exists()
        assert manager.config.temporary_path.exists()
        
        # Version file should exist
        assert manager.version_file.exists()
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_bootstrap_installation_creates_default_config(self, mock_subprocess, tmp_path):
        """Test that bootstrap creates default base configuration."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Mock git commands
        mock_subprocess.return_value = Mock(returncode=0)
        
        manager.bootstrap_installation()
        
        # Base identity file should exist and be valid
        identity_file = manager.config.base_path / "identity.yaml"
        assert identity_file.exists()
        
        with identity_file.open() as f:
            config = yaml.safe_load(f)
        
        # Should have expected structure
        assert "base_importance" in config
        assert "identity" in config
        assert "behaviors" in config
        assert "technical" in config
        assert config["base_importance"] == 0.7
        assert config["version"] == "1.0.0"
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_bootstrap_installation_creates_welcome_persona(self, mock_subprocess, tmp_path):
        """Test that bootstrap creates welcome persona."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Mock git commands
        mock_subprocess.return_value = Mock(returncode=0)
        
        manager.bootstrap_installation()
        
        # Welcome persona should exist
        welcome_file = manager.config.personas_path / "welcome.yaml"
        assert welcome_file.exists()
        
        with welcome_file.open() as f:
            persona = yaml.safe_load(f)
        
        assert persona["name"] == "welcome"
        assert persona["base_importance"] == 0.8
        assert persona["specialization_level"] == 1
        assert "behaviors" in persona
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_bootstrap_installation_initializes_git(self, mock_subprocess, tmp_path):
        """Test that bootstrap initializes git repository."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Mock git commands to succeed
        mock_subprocess.return_value = Mock(returncode=0)
        
        manager.bootstrap_installation()
        
        # Check that git init was called
        assert mock_subprocess.called
        git_init_called = any(
            call_args[0][0][0] == "git" and call_args[0][0][1] == "init" 
            for call_args in mock_subprocess.call_args_list
        )
        assert git_init_called
        
        # .gitignore should be created
        gitignore_file = helios_dir / ".gitignore"
        assert gitignore_file.exists()
        
        gitignore_content = gitignore_file.read_text()
        assert "*.tmp" in gitignore_content
        assert "*.bak" in gitignore_content
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_bootstrap_sets_git_config_when_needed(self, mock_subprocess, tmp_path):
        """Test that bootstrap sets git config when global config is missing."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Mock git config check to fail (no global config)
        def mock_run_side_effect(cmd, **kwargs):
            if len(cmd) >= 3 and cmd[0] == "git" and cmd[1] == "config" and cmd[2] == "user.email":
                # Simulate no global git config
                raise subprocess.CalledProcessError(1, cmd)
            return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_run_side_effect
        
        manager.bootstrap_installation()
        
        # Should have attempted git operations
        assert mock_subprocess.called
        
        # Check that git config operations were attempted
        config_calls = [
            call_args for call_args in mock_subprocess.call_args_list 
            if len(call_args[0][0]) >= 2 and call_args[0][0][0] == "git" and call_args[0][0][1] == "config"
        ]
        
        # Should have attempted to read and set config
        assert len(config_calls) >= 1
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_bootstrap_handles_git_failure_gracefully(self, mock_subprocess, tmp_path):
        """Test that bootstrap continues when git initialization fails."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Mock git to fail
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, ["git", "init"])
        
        # Bootstrap should still succeed (git is optional)
        manager.bootstrap_installation()
        
        # Other files should still be created
        assert manager.version_file.exists()
        assert manager.config.base_path.exists()
    
    def test_bootstrap_skips_existing_configs(self, tmp_path):
        """Test that bootstrap doesn't overwrite existing configurations."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Create directories and existing config
        manager.config.base_path.mkdir(parents=True, exist_ok=True)
        identity_file = manager.config.base_path / "identity.yaml"
        
        existing_config = {"custom": "config", "base_importance": 0.9}
        with identity_file.open('w') as f:
            yaml.safe_dump(existing_config, f)
        
        with patch('helios_mcp.bootstrap.subprocess.run'):
            manager.bootstrap_installation()
        
        # Existing config should be preserved
        with identity_file.open() as f:
            preserved_config = yaml.safe_load(f)
        
        assert preserved_config["custom"] == "config"
        assert preserved_config["base_importance"] == 0.9


class TestInstallationInfo:
    """Test installation information retrieval."""
    
    def test_get_installation_info_not_installed(self, tmp_path):
        """Test installation info for fresh installation."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        info = manager.get_installation_info()
        
        assert info["installed"] is False
        assert info["version"] is None
        assert info["install_date"] is None
    
    def test_get_installation_info_installed(self, tmp_path):
        """Test installation info for existing installation."""
        helios_dir = tmp_path / ".helios"
        helios_dir.mkdir()
        
        # Create version file
        version_file = helios_dir / ".helios_version"
        version_data = {
            "version": "0.1.0",
            "install_date": "2025-09-07T10:30:00",
            "last_boot": "2025-09-07T11:00:00"
        }
        
        with version_file.open('w') as f:
            yaml.safe_dump(version_data, f)
        
        manager = BootstrapManager(helios_dir)
        info = manager.get_installation_info()
        
        assert info["installed"] is True
        assert info["version"] == "0.1.0"
        assert info["install_date"] == "2025-09-07T10:30:00"
        assert info["last_boot"] == "2025-09-07T11:00:00"
    
    def test_get_installation_info_corrupted_version_file(self, tmp_path):
        """Test installation info with corrupted version file."""
        helios_dir = tmp_path / ".helios"
        helios_dir.mkdir()
        
        # Create corrupted version file
        version_file = helios_dir / ".helios_version"
        version_file.write_text("invalid: yaml: content: [")
        
        manager = BootstrapManager(helios_dir)
        info = manager.get_installation_info()
        
        assert info["installed"] is True
        assert info["version"] == "unknown"
        assert "error" in info


class TestBootTimestampUpdate:
    """Test boot timestamp updating functionality."""
    
    def test_update_last_boot_existing_installation(self, tmp_path):
        """Test updating boot timestamp for existing installation."""
        helios_dir = tmp_path / ".helios"
        helios_dir.mkdir()
        
        # Create existing version file
        version_file = helios_dir / ".helios_version"
        original_data = {
            "version": "0.1.0",
            "install_date": "2025-09-07T10:00:00",
            "last_boot": "2025-09-07T10:00:00"
        }
        
        with version_file.open('w') as f:
            yaml.safe_dump(original_data, f)
        
        manager = BootstrapManager(helios_dir)
        
        # Update boot timestamp
        with patch('helios_mcp.bootstrap.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.isoformat.return_value = "2025-09-07T12:00:00"
            mock_datetime.datetime.now.return_value = mock_now
            
            manager.update_last_boot()
        
        # Check updated data
        with version_file.open() as f:
            updated_data = yaml.safe_load(f)
        
        assert updated_data["version"] == "0.1.0"
        assert updated_data["install_date"] == "2025-09-07T10:00:00"  # Preserved
        assert updated_data["last_boot"] == "2025-09-07T12:00:00"  # Updated
    
    def test_update_last_boot_no_installation(self, tmp_path):
        """Test updating boot timestamp when not installed."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Should not crash when no installation exists
        manager.update_last_boot()
        
        # No version file should be created
        assert not manager.version_file.exists()


class TestBootstrapErrorHandling:
    """Test bootstrap error handling and cleanup."""
    
    @patch('helios_mcp.bootstrap.atomic_write_yaml')
    def test_bootstrap_cleanup_on_failure(self, mock_atomic_write, tmp_path):
        """Test cleanup when bootstrap fails."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Make atomic_write_yaml fail during version file creation
        def write_side_effect(path, data):
            if "version" in str(path):
                raise OSError("Disk full")
        
        mock_atomic_write.side_effect = write_side_effect
        
        # Bootstrap should fail and clean up
        with pytest.raises(OSError, match="Disk full"):
            manager.bootstrap_installation()
        
        # Version file should not exist after cleanup
        assert not manager.version_file.exists()
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    @patch('helios_mcp.bootstrap.atomic_write_yaml')
    def test_bootstrap_partial_success(self, mock_atomic_write, mock_subprocess, tmp_path):
        """Test bootstrap partial success scenarios."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        # Let git fail but other operations succeed
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, ["git", "init"])
        
        # Bootstrap should complete despite git failure
        manager.bootstrap_installation()
        
        # Version file should be created (bootstrap completed)
        mock_atomic_write.assert_called()
        
        # Check that version file creation was attempted
        version_calls = [call for call in mock_atomic_write.call_args_list 
                        if ".helios_version" in str(call[0][0])]
        assert len(version_calls) >= 1


class TestPrivateMethods:
    """Test private methods of BootstrapManager."""
    
    def test_create_directory_structure(self, tmp_path):
        """Test directory structure creation."""
        helios_dir = tmp_path / ".helios"
        manager = BootstrapManager(helios_dir)
        
        manager._create_directory_structure()
        
        # All required directories should exist
        assert helios_dir.exists()
        assert manager.config.base_path.exists()
        assert manager.config.personas_path.exists()
        assert manager.config.learned_path.exists()
        assert manager.config.temporary_path.exists()
    
    def test_create_version_file(self, tmp_path):
        """Test version file creation."""
        helios_dir = tmp_path / ".helios"
        helios_dir.mkdir()
        
        manager = BootstrapManager(helios_dir)
        
        with patch('helios_mcp.bootstrap.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.isoformat.return_value = "2025-09-07T10:00:00"
            mock_datetime.datetime.now.return_value = mock_now
            
            manager._create_version_file()
        
        # Version file should exist with correct data
        assert manager.version_file.exists()
        
        with manager.version_file.open() as f:
            version_data = yaml.safe_load(f)
        
        assert version_data["version"] == "0.1.0"
        assert version_data["install_date"] == "2025-09-07T10:00:00"
        assert version_data["last_boot"] == "2025-09-07T10:00:00"
        assert version_data["bootstrap_complete"] is True
    
    def test_cleanup_failed_bootstrap(self, tmp_path):
        """Test cleanup after failed bootstrap."""
        helios_dir = tmp_path / ".helios"
        helios_dir.mkdir()
        
        manager = BootstrapManager(helios_dir)
        
        # Create version file to simulate partial bootstrap
        manager.version_file.write_text("partial: bootstrap")
        assert manager.version_file.exists()
        
        # Cleanup should remove version file
        manager._cleanup_failed_bootstrap()
        assert not manager.version_file.exists()


class TestBootstrapIntegration:
    """Integration tests for bootstrap functionality."""
    
    @patch('helios_mcp.bootstrap.subprocess.run')
    def test_full_bootstrap_workflow(self, mock_subprocess, tmp_path):
        """Test complete bootstrap workflow from fresh install to ready state."""
        helios_dir = tmp_path / ".helios"
        
        # Mock git operations to succeed
        mock_subprocess.return_value = Mock(returncode=0)
        
        manager = BootstrapManager(helios_dir)
        
        # Should detect first install
        assert manager.is_first_install() is True
        
        # Bootstrap should complete successfully
        manager.bootstrap_installation()
        
        # Should no longer be first install
        assert manager.is_first_install() is False
        
        # Installation info should be correct
        info = manager.get_installation_info()
        assert info["installed"] is True
        assert info["version"] == "0.1.0"
        
        # Update boot timestamp should work
        manager.update_last_boot()
        
        # All expected files and directories should exist
        assert helios_dir.exists()
        assert (helios_dir / "base" / "identity.yaml").exists()
        assert (helios_dir / "personas" / "welcome.yaml").exists()
        assert (helios_dir / ".helios_version").exists()
        assert (helios_dir / ".gitignore").exists()
    
    def test_bootstrap_idempotent(self, tmp_path):
        """Test that bootstrap can be run multiple times safely."""
        helios_dir = tmp_path / ".helios"
        
        with patch('helios_mcp.bootstrap.subprocess.run'):
            manager = BootstrapManager(helios_dir)
            
            # First bootstrap
            manager.bootstrap_installation()
            first_info = manager.get_installation_info()
            
            # Verify initial files exist
            assert (helios_dir / "base" / "identity.yaml").exists()
            assert (helios_dir / "personas" / "welcome.yaml").exists()
            
            # Read config files to verify they don't get overwritten
            with (helios_dir / "base" / "identity.yaml").open() as f:
                first_base_config = yaml.safe_load(f)
            
            # Second bootstrap should not overwrite existing configs
            manager.bootstrap_installation()
            second_info = manager.get_installation_info()
            
            # Config files should be preserved (not overwritten)
            with (helios_dir / "base" / "identity.yaml").open() as f:
                second_base_config = yaml.safe_load(f)
            
            # The config content should be identical (not overwritten)
            assert first_base_config == second_base_config
            
            # Both should have same version
            assert first_info["version"] == second_info["version"]