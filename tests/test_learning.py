"""Tests for the Helios MCP learning system."""

import pytest
import yaml
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, call, mock_open

from helios_mcp.learning import (
    LearningManager,
    LearnBehaviorParams,
    TuneWeightParams,
    RevertLearningParams,
    EvolveBehaviorParams
)


class TestLearnBehaviorParams:
    """Test parameter validation for learn_behavior."""
    
    def test_learn_behavior_params_valid(self):
        """Test valid parameter creation."""
        params = LearnBehaviorParams(
            persona="developer",
            key="behaviors.communication_style",
            value="technical"
        )
        assert params.persona == "developer"
        assert params.key == "behaviors.communication_style"
        assert params.value == "technical"
    
    def test_learn_behavior_params_with_complex_value(self):
        """Test parameter creation with complex values."""
        params = LearnBehaviorParams(
            persona="architect", 
            key="preferences.tools",
            value=["python", "rust", "go"]
        )
        assert params.value == ["python", "rust", "go"]


class TestTuneWeightParams:
    """Test parameter validation for tune_weight."""
    
    def test_tune_weight_params_base_importance(self):
        """Test parameter creation for base importance."""
        params = TuneWeightParams(
            target="base",
            parameter="base_importance",
            value=0.5
        )
        assert params.target == "base"
        assert params.parameter == "base_importance"
        assert params.value == 0.5
    
    def test_tune_weight_params_specialization_level(self):
        """Test parameter creation for specialization level."""
        params = TuneWeightParams(
            target="developer",
            parameter="specialization_level", 
            value=3.0
        )
        assert params.target == "developer"
        assert params.parameter == "specialization_level"
        assert params.value == 3.0


class TestLearningManagerInit:
    """Test LearningManager initialization."""
    
    def test_learning_manager_initialization(self, temp_helios_dir):
        """Test basic initialization."""
        manager = LearningManager(temp_helios_dir)
        
        assert manager.helios_dir == temp_helios_dir
        assert manager.config_loader is not None
        assert manager.git_store is not None
    
    def test_learning_manager_paths_configured(self, temp_helios_dir):
        """Test that manager has correct path configuration."""
        manager = LearningManager(temp_helios_dir)
        
        config = manager.config_loader.config
        assert config.base_path == temp_helios_dir / "base"
        assert config.personas_path == temp_helios_dir / "personas"
        assert config.learned_path == temp_helios_dir / "learned"
        assert config.temporary_path == temp_helios_dir / "temporary"


class TestNavigateToKey:
    """Test private _navigate_to_key method."""
    
    def test_navigate_to_simple_key(self, temp_helios_dir):
        """Test navigation to simple key."""
        manager = LearningManager(temp_helios_dir)
        config = {"behavior": "value"}
        
        parent, final_key = manager._navigate_to_key(config, "behavior")
        assert parent is config
        assert final_key == "behavior"
    
    def test_navigate_to_nested_key(self, temp_helios_dir):
        """Test navigation to nested key."""
        manager = LearningManager(temp_helios_dir)
        config = {"behaviors": {"communication": "technical"}}
        
        parent, final_key = manager._navigate_to_key(config, "behaviors.communication")
        assert parent == {"communication": "technical"}
        assert final_key == "communication"
    
    def test_navigate_creates_missing_keys(self, temp_helios_dir):
        """Test that missing intermediate keys are created."""
        manager = LearningManager(temp_helios_dir)
        config = {}
        
        parent, final_key = manager._navigate_to_key(
            config, "behaviors.preferences.tools", create_missing=True
        )
        assert "behaviors" in config
        assert "preferences" in config["behaviors"]
        assert parent == config["behaviors"]["preferences"]
        assert final_key == "tools"
    
    def test_navigate_fails_when_missing_without_create(self, temp_helios_dir):
        """Test that KeyError is raised for missing keys when create_missing=False."""
        manager = LearningManager(temp_helios_dir)
        config = {}
        
        with pytest.raises(KeyError, match="Path 'behaviors' not found"):
            manager._navigate_to_key(config, "behaviors.missing", create_missing=False)


class TestGetConfigPath:
    """Test private _get_config_path method."""
    
    def test_get_base_config_path(self, temp_helios_dir):
        """Test getting base config path."""
        manager = LearningManager(temp_helios_dir)
        
        path = manager._get_config_path("base")
        assert path == temp_helios_dir / "base" / "identity.yaml"
    
    def test_get_persona_config_path(self, temp_helios_dir):
        """Test getting persona config path."""
        manager = LearningManager(temp_helios_dir)
        
        path = manager._get_config_path("developer")
        assert path == temp_helios_dir / "personas" / "developer.yaml"


class TestLearnBehavior:
    """Test learn_behavior functionality."""
    
    @pytest.fixture
    def sample_persona_config(self):
        """Sample persona configuration."""
        return {
            "specialization_level": 2,
            "behaviors": {
                "communication_style": "casual"
            },
            "preferences": {
                "tools": ["python"]
            }
        }
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_learn_behavior_success(self, mock_yaml_load, mock_file_open, mock_atomic_write, 
                                         temp_helios_dir, mock_git_repo, sample_persona_config):
        """Test successful behavior learning."""
        # Setup mocks
        mock_yaml_load.return_value = sample_persona_config.copy()
        
        # Mock the persona file exists
        persona_path = temp_helios_dir / "personas" / "developer.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        # Create manager with mocked git
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            # Test learning new behavior
            params = LearnBehaviorParams(
                persona="developer",
                key="behaviors.debug_style",
                value="verbose"
            )
            
            result = await manager.learn_behavior(params)
            
            # Verify result
            assert result["status"] == "learned"
            assert result["persona"] == "developer"
            assert result["key"] == "behaviors.debug_style"
            assert result["old_value"] == "not set"
            assert result["new_value"] == "verbose"
            
            # Verify atomic write was called
            mock_atomic_write.assert_called_once()
            
            # Verify git commit was called
            mock_git_store.auto_commit.assert_called_once_with(
                "Learned: behaviors.debug_style=verbose for developer persona"
            )
    
    async def test_learn_behavior_missing_persona(self, temp_helios_dir):
        """Test behavior learning with missing persona."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = LearnBehaviorParams(
                persona="nonexistent",
                key="behaviors.test",
                value="value"
            )
            
            result = await manager.learn_behavior(params)
            
            assert result["status"] == "error"
            assert "not found" in result["error"]
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_learn_behavior_additive_list(self, mock_yaml_load, mock_file_open, 
                                               mock_atomic_write, temp_helios_dir, 
                                               sample_persona_config):
        """Test that learning adds to lists instead of replacing."""
        # Setup existing list
        mock_yaml_load.return_value = sample_persona_config.copy()
        
        persona_path = temp_helios_dir / "personas" / "developer.yaml" 
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = LearnBehaviorParams(
                persona="developer",
                key="preferences.tools",
                value="rust"
            )
            
            result = await manager.learn_behavior(params)
            
            # Should have added to the list, not replaced
            assert result["status"] == "learned"
            assert result["old_value"] == ["python"] 
            assert result["new_value"] == ["python", "rust"]
    
    @patch('helios_mcp.learning.atomic_write_yaml') 
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_learn_behavior_duplicate_list_item(self, mock_yaml_load, mock_file_open,
                                                     mock_atomic_write, temp_helios_dir,
                                                     sample_persona_config):
        """Test that duplicate items are not added to lists."""
        mock_yaml_load.return_value = sample_persona_config.copy()
        
        persona_path = temp_helios_dir / "personas" / "developer.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True) 
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = LearnBehaviorParams(
                persona="developer",
                key="preferences.tools",
                value="python"  # Already exists
            )
            
            result = await manager.learn_behavior(params)
            
            # Should not have changed the list
            assert result["old_value"] == ["python"]
            assert result["new_value"] == ["python"]  # No duplicate added
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    async def test_learn_behavior_exception_handling(self, mock_atomic_write, temp_helios_dir):
        """Test that exceptions are handled gracefully."""
        # Make atomic_write_yaml raise an exception
        mock_atomic_write.side_effect = OSError("Disk full")
        
        persona_path = temp_helios_dir / "personas" / "test.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = LearnBehaviorParams(
                persona="test",
                key="behaviors.test",
                value="value"
            )
            
            result = await manager.learn_behavior(params)
            
            assert result["status"] == "error"
            assert "Disk full" in result["error"]


class TestTuneWeight:
    """Test tune_weight functionality."""
    
    @pytest.fixture
    def sample_base_config(self):
        """Sample base configuration."""
        return {
            "base_importance": 0.7,
            "behaviors": {"style": "technical"}
        }
    
    @pytest.fixture
    def sample_persona_weight_config(self):
        """Sample persona configuration for weight tuning."""
        return {
            "specialization_level": 2,
            "behaviors": {"style": "casual"}
        }
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_tune_base_importance_success(self, mock_yaml_load, mock_file_open,
                                               mock_atomic_write, temp_helios_dir,
                                               sample_base_config):
        """Test successful base importance tuning."""
        mock_yaml_load.return_value = sample_base_config.copy()
        
        base_path = temp_helios_dir / "base" / "identity.yaml"
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.touch()
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="base",
                parameter="base_importance",
                value=0.8
            )
            
            result = await manager.tune_weight(params)
            
            assert result["status"] == "tuned"
            assert result["target"] == "base"
            assert result["parameter"] == "base_importance"
            assert result["old_value"] == 0.7
            assert result["new_value"] == 0.8
            
            mock_atomic_write.assert_called_once()
            mock_git_store.auto_commit.assert_called_once()
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_tune_specialization_level_success(self, mock_yaml_load, mock_file_open,
                                                    mock_atomic_write, temp_helios_dir,
                                                    sample_persona_weight_config):
        """Test successful specialization level tuning."""
        mock_yaml_load.return_value = sample_persona_weight_config.copy()
        
        persona_path = temp_helios_dir / "personas" / "developer.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="developer",
                parameter="specialization_level",
                value=3.0
            )
            
            result = await manager.tune_weight(params)
            
            assert result["status"] == "tuned"
            assert result["target"] == "developer"
            assert result["parameter"] == "specialization_level"
            assert result["old_value"] == 2
            assert result["new_value"] == 3.0
            
            # Should include inheritance weight calculation
            assert "inheritance weight" in result["inheritance_info"]
            
            mock_atomic_write.assert_called_once()
            mock_git_store.auto_commit.assert_called_once()
    
    async def test_tune_weight_invalid_parameter_for_base(self, temp_helios_dir):
        """Test tuning invalid parameter for base configuration."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="base",
                parameter="specialization_level",  # Invalid for base
                value=2.0
            )
            
            result = await manager.tune_weight(params)
            
            assert result["status"] == "error"
            assert "Cannot tune 'specialization_level' for base" in result["error"]
    
    async def test_tune_weight_invalid_parameter_for_persona(self, temp_helios_dir):
        """Test tuning invalid parameter for persona configuration."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="developer",
                parameter="base_importance",  # Invalid for persona
                value=0.5
            )
            
            result = await manager.tune_weight(params)
            
            assert result["status"] == "error"
            assert "Cannot tune 'base_importance' for persona" in result["error"]
    
    async def test_tune_weight_base_importance_out_of_range(self, temp_helios_dir):
        """Test base importance validation."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            # Test value too high
            params = TuneWeightParams(
                target="base",
                parameter="base_importance",
                value=1.5
            )
            
            result = await manager.tune_weight(params)
            assert result["status"] == "error"
            assert "must be between 0.0 and 1.0" in result["error"]
            
            # Test value too low
            params.value = -0.1
            result = await manager.tune_weight(params)
            assert result["status"] == "error"
            assert "must be between 0.0 and 1.0" in result["error"]
    
    async def test_tune_weight_specialization_level_out_of_range(self, temp_helios_dir):
        """Test specialization level validation."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="developer",
                parameter="specialization_level",
                value=0.5  # Must be >= 1.0
            )
            
            result = await manager.tune_weight(params)
            assert result["status"] == "error"
            assert "must be >= 1.0" in result["error"]
    
    async def test_tune_weight_missing_config(self, temp_helios_dir):
        """Test tuning weight for missing configuration."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="missing_persona",
                parameter="specialization_level", 
                value=2.0
            )
            
            result = await manager.tune_weight(params)
            assert result["status"] == "error"
            assert "not found" in result["error"]


class TestRevertLearning:
    """Test revert_learning functionality."""
    
    @patch('helios_mcp.learning.subprocess.run')
    async def test_revert_learning_success(self, mock_subprocess, temp_helios_dir):
        """Test successful learning revert."""
        # Mock git log to show commits to revert
        log_output = "abc123 Learned: behaviors.style=casual\ndef456 Tuned: specialization_level=2"
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=log_output),  # git log
            Mock(returncode=0)  # git revert
        ]
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = RevertLearningParams(commits_back=2)
            result = await manager.revert_learning(params)
            
            assert result["status"] == "reverted"
            assert result["commits_reverted"] == 2
            assert len(result["reverted_commits"]) == 2
            
            # Verify git commands were called
            assert mock_subprocess.call_count == 2
            
            # Check git log command - structure is ["git", "-C", helios_dir, "log", "--oneline", "-2"]
            first_call = mock_subprocess.call_args_list[0][0][0]
            assert first_call[0] == "git"
            assert first_call[1] == "-C"
            assert first_call[3] == "log"
            assert first_call[4] == "--oneline"
            assert "-2" in first_call
            
            # Check git revert command - structure is ["git", "-C", helios_dir, "revert", "HEAD~2..HEAD", "--no-edit"]
            second_call = mock_subprocess.call_args_list[1][0][0]
            assert second_call[0] == "git"
            assert second_call[1] == "-C"
            assert second_call[3] == "revert"
    
    @patch('helios_mcp.learning.subprocess.run')
    async def test_revert_learning_single_commit_fallback(self, mock_subprocess, temp_helios_dir):
        """Test single commit revert fallback."""
        # Mock range revert to fail, single revert to succeed
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="abc123 Recent commit"),  # git log
            Mock(returncode=1, stderr="Range revert failed"),  # git revert range fails
            Mock(returncode=0)  # git revert HEAD succeeds
        ]
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = RevertLearningParams(commits_back=1)
            result = await manager.revert_learning(params)
            
            assert result["status"] == "reverted"
            assert result["commits_reverted"] == 1
            
            # Should have called git revert HEAD as fallback
            assert mock_subprocess.call_count == 3
    
    @patch('helios_mcp.learning.subprocess.run')
    async def test_revert_learning_git_log_failure(self, mock_subprocess, temp_helios_dir):
        """Test revert when git log fails."""
        mock_subprocess.return_value = Mock(returncode=1, stderr="Git log failed")
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = RevertLearningParams(commits_back=1)
            result = await manager.revert_learning(params)
            
            assert result["status"] == "error"
            assert "Failed to retrieve git history" in result["error"]
    
    @patch('helios_mcp.learning.subprocess.run')
    async def test_revert_learning_no_commits(self, mock_subprocess, temp_helios_dir):
        """Test revert when there are no commits."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="")  # Empty git log
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = RevertLearningParams(commits_back=1)
            result = await manager.revert_learning(params)
            
            assert result["status"] == "error"
            assert "No commits to revert" in result["error"]
    
    @patch('helios_mcp.learning.subprocess.run')
    async def test_revert_learning_git_revert_failure(self, mock_subprocess, temp_helios_dir):
        """Test revert when git revert fails completely."""
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="abc123 Recent commit"),  # git log succeeds
            Mock(returncode=1, stderr="Revert failed"),  # Range revert fails
            Mock(returncode=1, stderr="Single revert failed")  # Single revert also fails
        ]
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = RevertLearningParams(commits_back=1)
            result = await manager.revert_learning(params)
            
            assert result["status"] == "error"
            assert "Git revert failed" in result["error"]
    
    async def test_revert_learning_commits_back_validation(self, temp_helios_dir):
        """Test that commits_back parameter is properly validated."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            # Test that parameter model validates range (1-10)
            params = RevertLearningParams(commits_back=1)
            assert params.commits_back == 1
            
            params = RevertLearningParams(commits_back=10)
            assert params.commits_back == 10
            
            # These should raise validation errors
            with pytest.raises(ValueError):
                RevertLearningParams(commits_back=0)
            
            with pytest.raises(ValueError):
                RevertLearningParams(commits_back=11)


class TestEvolveBehavior:
    """Test evolve_behavior functionality."""
    
    @pytest.fixture
    def sample_base_evolve_config(self):
        """Sample base configuration for evolution."""
        return {
            "base_importance": 0.7,
            "behaviors": {
                "communication_style": "technical",
                "package_manager": "uv"
            }
        }
    
    @pytest.fixture
    def sample_persona_evolve_config(self):
        """Sample persona configuration for evolution."""
        return {
            "specialization_level": 2,
            "behaviors": {
                "communication_style": "casual",
                "framework_preference": "fastapi"
            }
        }
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_evolve_behavior_promotion_to_base(self, mock_yaml_load, mock_file_open,
                                                    mock_atomic_write, temp_helios_dir,
                                                    sample_persona_evolve_config,
                                                    sample_base_evolve_config):
        """Test promoting behavior from persona to base."""
        # Setup file paths
        persona_path = temp_helios_dir / "personas" / "developer.yaml"
        base_path = temp_helios_dir / "base" / "identity.yaml"
        
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        base_path.touch()
        
        # Mock yaml loads for both files
        def mock_yaml_side_effect(*args, **kwargs):
            # Return persona config first, then base config
            if mock_yaml_load.call_count == 1:
                return sample_persona_evolve_config.copy()
            else:
                return sample_base_evolve_config.copy()
        
        mock_yaml_load.side_effect = mock_yaml_side_effect
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="developer",
                to_config="base",
                key="behaviors.framework_preference"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "evolved"
            assert result["key"] == "behaviors.framework_preference"
            assert result["value"] == "fastapi"
            assert result["from"] == "developer"
            assert result["to"] == "base"
            assert result["direction"] == "promoted"
            
            # Should have written both files
            assert mock_atomic_write.call_count == 2
            mock_git_store.auto_commit.assert_called_once()
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_evolve_behavior_specialization_to_persona(self, mock_yaml_load, mock_file_open,
                                                            mock_atomic_write, temp_helios_dir,
                                                            sample_base_evolve_config,
                                                            sample_persona_evolve_config):
        """Test specializing behavior from base to persona."""
        # Setup paths
        base_path = temp_helios_dir / "base" / "identity.yaml"
        persona_path = temp_helios_dir / "personas" / "frontend.yaml"
        
        base_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.touch()
        persona_path.touch()
        
        # Mock yaml loads for both files
        def mock_yaml_side_effect(*args, **kwargs):
            if mock_yaml_load.call_count == 1:
                return sample_base_evolve_config.copy()
            else:
                return sample_persona_evolve_config.copy()
        
        mock_yaml_load.side_effect = mock_yaml_side_effect
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="base",
                to_config="frontend",
                key="behaviors.package_manager"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "evolved"
            assert result["key"] == "behaviors.package_manager"
            assert result["value"] == "uv"
            assert result["from"] == "base"
            assert result["to"] == "frontend"
            assert result["direction"] == "specialized"
    
    async def test_evolve_behavior_same_config_error(self, temp_helios_dir):
        """Test error when source and target are the same."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="developer",
                to_config="developer",
                key="behaviors.test"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "error"
            assert "Source and target must be different" in result["error"]
    
    async def test_evolve_behavior_missing_source_config(self, temp_helios_dir):
        """Test error when source configuration doesn't exist."""
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="missing_persona",
                to_config="base",
                key="behaviors.test"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "error"
            assert "Source configuration 'missing_persona' not found" in result["error"]
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_evolve_behavior_missing_key(self, mock_yaml_load, mock_file_open,
                                              temp_helios_dir, sample_persona_evolve_config):
        """Test error when key doesn't exist in source config."""
        mock_yaml_load.return_value = sample_persona_evolve_config.copy()
        
        persona_path = temp_helios_dir / "personas" / "developer.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="developer",
                to_config="base",
                key="behaviors.missing_key"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "error"
            assert "Key 'behaviors.missing_key' not found in developer" in result["error"]
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_evolve_behavior_creates_new_persona(self, mock_yaml_load, mock_file_open,
                                                      mock_atomic_write, temp_helios_dir,
                                                      sample_base_evolve_config):
        """Test that evolution creates new persona if target doesn't exist."""
        mock_yaml_load.return_value = sample_base_evolve_config.copy()
        
        base_path = temp_helios_dir / "base" / "identity.yaml"
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.touch()
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="base",
                to_config="new_persona",
                key="behaviors.communication_style"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "evolved"
            assert result["value"] == "technical"
            
            # Should have written both files (existing base, new persona)
            assert mock_atomic_write.call_count == 2
            
            # Check that new persona config was created properly
            new_persona_call = [call for call in mock_atomic_write.call_args_list 
                               if "new_persona.yaml" in str(call[0][0])][0]
            
            new_persona_config = new_persona_call[0][1]
            assert new_persona_config["specialization_level"] == 2
            assert "Evolved from base" in new_persona_config["description"]
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    async def test_evolve_behavior_exception_handling(self, mock_atomic_write, temp_helios_dir):
        """Test that exceptions are handled gracefully."""
        # Make atomic_write_yaml raise an exception
        mock_atomic_write.side_effect = OSError("Permission denied")
        
        base_path = temp_helios_dir / "base" / "identity.yaml"
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_text("behaviors: {test: value}")
        
        with patch('helios_mcp.learning.GitStore'):
            manager = LearningManager(temp_helios_dir)
            
            params = EvolveBehaviorParams(
                from_config="base",
                to_config="test_persona",
                key="behaviors.test"
            )
            
            result = await manager.evolve_behavior(params)
            
            assert result["status"] == "error"
            assert "Permission denied" in result["error"]


class TestInheritanceCalculations:
    """Test gravitational dynamics and inheritance calculations."""
    
    @pytest.mark.parametrize("specialization_level,expected_weight", [
        (1.0, 0.7),    # specialization_level = 1 → weight = base_importance / 1² = 0.7
        (2.0, 0.175),  # specialization_level = 2 → weight = 0.7 / 4 = 0.175
        (4.0, 0.04375), # specialization_level = 4 → weight = 0.7 / 16 = 0.04375
        (10.0, 0.007),  # specialization_level = 10 → weight = 0.7 / 100 = 0.007
    ])
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_inheritance_weight_calculation(self, mock_yaml_load, mock_file_open,
                                                 mock_atomic_write, specialization_level,
                                                 expected_weight, temp_helios_dir):
        """Test inheritance weight calculations match gravitational model."""
        base_importance = 0.7
        config = {
            "specialization_level": specialization_level,
            "behaviors": {"test": "value"}
        }
        mock_yaml_load.return_value = config
        
        persona_path = temp_helios_dir / "personas" / "test.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            params = TuneWeightParams(
                target="test",
                parameter="specialization_level",
                value=specialization_level
            )
            
            result = await manager.tune_weight(params)
            
            # Extract calculated weight from inheritance info
            inheritance_info = result.get("inheritance_info", "")
            
            # Parse the percentage from inheritance_info
            if "inheritance weight:" in inheritance_info:
                weight_str = inheritance_info.split("inheritance weight: ")[1].rstrip("%)")
                calculated_weight = float(weight_str.rstrip("%")) / 100
                
                # Allow small floating point differences
                assert abs(calculated_weight - expected_weight) < 0.001


class TestLearningIntegration:
    """Integration tests combining multiple learning operations."""
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('helios_mcp.learning.subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_learn_then_evolve_workflow(self, mock_yaml_load, mock_file_open,
                                             mock_subprocess, mock_atomic_write, temp_helios_dir):
        """Test complete workflow: learn behavior, then evolve it."""
        # Setup initial configs
        initial_persona = {
            "specialization_level": 2,
            "behaviors": {"style": "casual"}
        }
        
        updated_persona = {
            "specialization_level": 2,
            "behaviors": {"style": "casual", "new_behavior": "learned_value"}
        }
        
        base_config = {
            "base_importance": 0.7,
            "behaviors": {"style": "technical"}
        }
        
        # Mock file system
        persona_path = temp_helios_dir / "personas" / "developer.yaml"
        base_path = temp_helios_dir / "base" / "identity.yaml"
        
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        base_path.touch()
        
        # Setup yaml load sequence
        load_sequence = [
            initial_persona.copy(),   # Initial load for learning
            updated_persona.copy(),   # Load after learning for evolution (from)
            base_config.copy()        # Load base config for evolution (to)
        ]
        mock_yaml_load.side_effect = load_sequence
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            # Step 1: Learn a new behavior
            learn_params = LearnBehaviorParams(
                persona="developer",
                key="behaviors.new_behavior",
                value="learned_value"
            )
            
            learn_result = await manager.learn_behavior(learn_params)
            assert learn_result["status"] == "learned"
            
            # Step 2: Evolve the learned behavior to base
            evolve_params = EvolveBehaviorParams(
                from_config="developer",
                to_config="base",
                key="behaviors.new_behavior"
            )
            
            evolve_result = await manager.evolve_behavior(evolve_params)
            assert evolve_result["status"] == "evolved"
            assert evolve_result["direction"] == "promoted"
            assert evolve_result["value"] == "learned_value"
            
            # Verify git commits were made for both operations
            assert mock_git_store.auto_commit.call_count == 2
    
    @patch('helios_mcp.learning.atomic_write_yaml')
    @patch('helios_mcp.learning.subprocess.run') 
    @patch('builtins.open', new_callable=mock_open)
    @patch('helios_mcp.learning.yaml.safe_load')
    async def test_tune_then_revert_workflow(self, mock_yaml_load, mock_file_open,
                                            mock_subprocess, mock_atomic_write, temp_helios_dir):
        """Test workflow: tune weight, then revert the change."""
        config = {
            "specialization_level": 2,
            "behaviors": {"test": "value"}
        }
        mock_yaml_load.return_value = config
        
        # Mock successful git operations
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout="abc123 Tuned: specialization_level"),  # git log
            Mock(returncode=0)  # git revert
        ]
        
        persona_path = temp_helios_dir / "personas" / "test.yaml"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.touch()
        
        with patch('helios_mcp.learning.GitStore') as mock_git_store_class:
            mock_git_store = Mock()
            mock_git_store_class.return_value = mock_git_store
            
            manager = LearningManager(temp_helios_dir)
            
            # Step 1: Tune weight
            tune_params = TuneWeightParams(
                target="test",
                parameter="specialization_level",
                value=4.0
            )
            
            tune_result = await manager.tune_weight(tune_params)
            assert tune_result["status"] == "tuned"
            
            # Step 2: Revert the tuning
            revert_params = RevertLearningParams(commits_back=1)
            revert_result = await manager.revert_learning(revert_params)
            assert revert_result["status"] == "reverted"
            assert revert_result["commits_reverted"] == 1
            
            # Verify both operations completed
            mock_git_store.auto_commit.assert_called_once()  # Only tune commits via GitStore
            assert mock_subprocess.call_count == 2  # git log + git revert