"""Tests for configuration validation functionality."""

import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
import yaml

from helios_mcp.validation import ConfigValidator


class TestConfigValidator:
    """Test configuration validation."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def validator(self, temp_dir):
        """Create ConfigValidator instance."""
        return ConfigValidator(temp_dir)
    
    def test_validate_base_config_valid(self, validator):
        """Test validation of valid base configuration."""
        config = {
            "base_importance": 0.7,
            "behaviors": {
                "style": "technical"
            },
            "identity": {
                "role": "assistant"
            }
        }
        valid, error = validator.validate_base_config(config)
        assert valid is True
        assert error is None
    
    def test_validate_base_config_missing_field(self, validator):
        """Test validation with missing required field."""
        config = {
            "behaviors": {"style": "technical"}
            # Missing base_importance
        }
        valid, error = validator.validate_base_config(config)
        assert valid is False
        assert "base_importance" in error
    
    def test_validate_base_config_invalid_range(self, validator):
        """Test validation with out-of-range value."""
        config = {
            "base_importance": 1.5,  # > 1.0
            "behaviors": {"style": "technical"}
        }
        valid, error = validator.validate_base_config(config)
        assert valid is False
        assert "0.0 and 1.0" in error
    
    def test_validate_persona_config_valid(self, validator):
        """Test validation of valid persona configuration."""
        config = {
            "specialization_level": 2,
            "behaviors": {
                "focus": "coding"
            }
        }
        valid, error = validator.validate_persona_config(config)
        assert valid is True
        assert error is None
    
    def test_validate_persona_config_invalid_level(self, validator):
        """Test validation with invalid specialization level."""
        config = {
            "specialization_level": 0,  # < 1
            "behaviors": {"focus": "coding"}
        }
        valid, error = validator.validate_persona_config(config)
        assert valid is False
        assert "specialization_level" in error
    
    def test_validate_yaml_file_valid(self, validator, temp_dir):
        """Test YAML file validation."""
        yaml_file = temp_dir / "test.yaml"
        yaml_file.write_text(yaml.dump({"key": "value"}))
        
        valid, error = validator.validate_yaml_syntax(yaml_file)
        assert valid is True
        assert error is None
    
    def test_validate_yaml_file_invalid_syntax(self, validator, temp_dir):
        """Test invalid YAML syntax detection."""
        yaml_file = temp_dir / "test.yaml"
        yaml_file.write_text("invalid: yaml: syntax:")
        
        valid, error = validator.validate_yaml_syntax(yaml_file)
        assert valid is False
        assert "YAML" in error
    
    def test_validate_yaml_file_missing(self, validator, temp_dir):
        """Test missing file handling."""
        yaml_file = temp_dir / "missing.yaml"
        
        valid, error = validator.validate_yaml_syntax(yaml_file)
        assert valid is False
        assert "does not exist" in error
    
    @patch('subprocess.run')
    def test_recover_from_corruption_git(self, mock_run, validator, temp_dir):
        """Test recovery from corruption using git."""
        # Setup git directory
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        
        corrupted_file = temp_dir / "base" / "identity.yaml"
        corrupted_file.parent.mkdir(parents=True)
        corrupted_file.write_text("corrupted")
        
        # Mock successful git checkout
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        # Create a validator with the temp_dir as helios_dir
        validator = ConfigValidator(temp_dir)
        
        assert validator.recover_from_corruption(corrupted_file) is True
        mock_run.assert_called_once()
    
    def test_recover_from_corruption_defaults(self, validator, temp_dir):
        """Test recovery by creating defaults."""
        missing_file = temp_dir / "base" / "identity.yaml"
        missing_file.parent.mkdir(parents=True)
        
        assert validator.recover_from_corruption(missing_file) is True
        assert missing_file.exists()
        
        # Check default was created
        with open(missing_file) as f:
            data = yaml.safe_load(f)
        assert "base_importance" in data
    
    def test_validate_all_configs_success(self, validator, temp_dir):
        """Test validation of all configurations."""
        # Create valid configs
        base_dir = temp_dir / "base"
        base_dir.mkdir()
        (base_dir / "identity.yaml").write_text(yaml.dump({
            "base_importance": 0.7,
            "behaviors": {}
        }))
        
        personas_dir = temp_dir / "personas"
        personas_dir.mkdir()
        (personas_dir / "test.yaml").write_text(yaml.dump({
            "specialization_level": 2,
            "behaviors": {}
        }))
        
        issues = validator.validate_all_configs(temp_dir)
        assert len(issues) == 0
    
    def test_validate_all_configs_with_issues(self, validator, temp_dir):
        """Test validation finding issues."""
        # Create invalid config
        base_dir = temp_dir / "base"
        base_dir.mkdir()
        (base_dir / "identity.yaml").write_text("invalid: yaml: syntax:")
        
        issues = validator.validate_all_configs(temp_dir)
        assert len(issues) > 0
        assert any("identity.yaml" in issue for issue in issues)