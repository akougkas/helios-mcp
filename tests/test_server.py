"""Tests for Helios MCP server functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import yaml
import tempfile

from helios_mcp.server import create_server
from helios_mcp.config import HeliosConfig, ConfigLoader
from helios_mcp.inheritance import InheritanceCalculator, BehaviorMerger, create_behavior_merger
from helios_mcp.git_store import GitStore


class TestServerCreation:
    """Test MCP server creation and configuration."""
    
    @pytest.mark.asyncio
    async def test_create_server_default_dir(self):
        """Test server creation with default directory."""
        server = create_server()
        
        assert server is not None
        assert server.name == "Helios"
        
        # Should have registered tools
        tools = await server.get_tools()
        tool_names = set(tools.keys())
        
        expected_tools = {
            "get_base_config",
            "get_active_persona", 
            "merge_behaviors",
            "commit_changes",
            "list_personas",
            "update_preference",
            "search_patterns"
        }
        
        for tool_name in expected_tools:
            assert tool_name in tool_names
    
    def test_create_server_custom_dir(self, temp_helios_dir):
        """Test server creation with custom directory."""
        server = create_server(temp_helios_dir)
        
        assert server is not None
        assert server.name == "Helios"
        
        # Directory should be created
        assert temp_helios_dir.exists()
        assert (temp_helios_dir / "base").exists()
        assert (temp_helios_dir / "personas").exists()
    
    @pytest.mark.asyncio
    async def test_server_tools_registered(self):
        """Test that all required tools are registered correctly."""
        server = create_server()
        tools = await server.get_tools()
        
        # Check each tool has proper metadata
        base_config_tool = tools.get("get_base_config")
        assert base_config_tool is not None
        assert "config" in base_config_tool.tags
        assert "base" in base_config_tool.tags
        assert "Load the base configuration" in base_config_tool.description
        
        merge_tool = tools.get("merge_behaviors")
        assert merge_tool is not None
        assert "inheritance" in merge_tool.tags
        assert "behaviors" in merge_tool.tags
        assert "weighted inheritance" in merge_tool.description


class TestInheritanceCalculations:
    """Test core inheritance calculation logic."""
    
    @pytest.mark.parametrize("base_importance,specialization_level,expected_weight", [
        (0.7, 1, 0.7),      # Low specialization = high base influence
        (0.7, 2, 0.175),    # 2x specialization = 1/4 base influence  
        (0.8, 3, 0.089),    # 3x specialization = 1/9 base influence
        (1.0, 1, 1.0),      # Perfect base importance
        (1.0, 10, 0.01),    # High specialization = minimal base influence
    ])
    def test_inheritance_weight_calculation(self, base_importance, specialization_level, expected_weight):
        """Test inheritance weight calculation formula."""
        calculator = InheritanceCalculator()
        
        weight = calculator.calculate_weight(
            base_importance=base_importance,
            specialization_level=specialization_level
        )
        
        assert abs(weight - expected_weight) < 0.001
    
    def test_inheritance_bounds_clamping(self):
        """Test that inheritance weights are clamped to valid bounds."""
        calculator = InheritanceCalculator()
        
        # Very high specialization should clamp to min_weight
        weight = calculator.calculate_weight(base_importance=0.1, specialization_level=100)
        assert weight >= 0.01  # Should be at minimum
        
        # Very low specialization should clamp to max_weight  
        weight = calculator.calculate_weight(base_importance=1.0, specialization_level=1)
        assert weight <= 0.99  # Should be at maximum
    
    def test_inheritance_validation(self):
        """Test inheritance parameter validation."""
        calculator = InheritanceCalculator()
        
        # Invalid base_importance
        with pytest.raises(ValueError, match="base_importance must be between 0.0 and 1.0"):
            calculator.calculate_weight(base_importance=1.5, specialization_level=2)
            
        with pytest.raises(ValueError, match="base_importance must be between 0.0 and 1.0"):
            calculator.calculate_weight(base_importance=-0.1, specialization_level=2)
        
        # Invalid specialization_level
        with pytest.raises(ValueError, match="specialization_level must be >= 1"):
            calculator.calculate_weight(base_importance=0.7, specialization_level=0)
    
    def test_behavior_merger_numeric_values(self):
        """Test behavior merging for numeric values."""
        merger = BehaviorMerger()
        
        base_config = {"priority": 10, "confidence": 0.9}
        persona_config = {"priority": 2, "confidence": 0.5}
        
        merged = merger.merge_behaviors(
            base_config, persona_config, 
            inheritance_weight=0.8  # Strong base influence
        )
        
        # Should be weighted average: base * 0.8 + persona * 0.2
        expected_priority = 10 * 0.8 + 2 * 0.2  # 8.4
        expected_confidence = 0.9 * 0.8 + 0.5 * 0.2  # 0.82
        
        assert abs(merged["priority"] - expected_priority) < 0.001
        assert abs(merged["confidence"] - expected_confidence) < 0.001
    
    def test_behavior_merger_string_values(self):
        """Test behavior merging for string values."""
        merger = BehaviorMerger()
        
        base_config = {"style": "formal"}
        persona_config = {"style": "casual"}
        
        # High inheritance weight should choose base
        merged = merger.merge_behaviors(
            base_config, persona_config,
            inheritance_weight=0.8
        )
        assert merged["style"] == "formal"
        
        # Low inheritance weight should choose persona
        merged = merger.merge_behaviors(
            base_config, persona_config,
            inheritance_weight=0.2
        )
        assert merged["style"] == "casual"
    
    def test_behavior_merger_nested_dicts(self):
        """Test behavior merging for nested dictionaries."""
        merger = BehaviorMerger()
        
        base_config = {
            "communication": {
                "tone": "professional",
                "length": "detailed",
                "formality": 0.8
            }
        }
        
        persona_config = {
            "communication": {
                "tone": "friendly", 
                "style": "conversational",
                "formality": 0.3
            }
        }
        
        merged = merger.merge_behaviors(
            base_config, persona_config,
            inheritance_weight=0.6
        )
        
        comm = merged["communication"]
        assert comm["tone"] == "professional"  # Base wins with weight > 0.5
        assert comm["style"] == "conversational"  # Only in persona
        assert comm["length"] == "detailed"  # Only in base
        
        # Numeric value should be weighted average
        expected_formality = 0.8 * 0.6 + 0.3 * 0.4
        assert abs(comm["formality"] - expected_formality) < 0.001
    
    def test_behavior_merger_list_handling(self):
        """Test behavior merging for list values."""
        merger = BehaviorMerger()
        
        base_config = {"tools": ["python", "rust", "go"]}
        persona_config = {"tools": ["javascript", "typescript", "python"]}
        
        # High base weight should favor base list
        merged = merger.merge_behaviors(
            base_config, persona_config,
            inheritance_weight=0.8
        )
        
        tools = merged["tools"]
        assert "python" in tools
        assert "rust" in tools  # From base
        assert "javascript" in tools  # From persona
        assert tools.index("python") < tools.index("javascript")  # Base first


class TestToolFunctions:
    """Test individual MCP tool functions with mock data."""
    
    @pytest.mark.asyncio
    async def test_get_base_config_success(self, test_client, sample_base_config):
        """Test get_base_config tool with valid data."""
        result = await test_client.call_tool("get_base_config")
        
        assert result["status"] == "success"
        assert "config" in result
        assert result["config"]["base_importance"] == sample_base_config["base_importance"]
        assert "behaviors" in result["config"]
    
    @pytest.mark.asyncio
    async def test_get_base_config_missing_file(self, temp_helios_dir):
        """Test get_base_config with missing configuration file."""
        from tests.conftest import MockTestClient
        
        # Create server with empty directory
        server = create_server(temp_helios_dir)
        client = MockTestClient(server)
        
        result = await client.call_tool("get_base_config")
        
        # Should create default config and succeed
        assert result["status"] == "success"
        assert "config" in result
        assert "base_importance" in result["config"]
    
    @pytest.mark.asyncio
    async def test_get_active_persona_not_found(self, test_client):
        """Test get_active_persona with non-existent persona."""
        result = await test_client.call_tool("get_active_persona", persona_name="nonexistent")
        
        assert result["status"] == "not_found"
        assert "persona" in result  # Should return sample structure
        assert "specialization_level" in result["persona"]
    
    @pytest.mark.asyncio
    async def test_get_active_persona_success(self, test_client, sample_persona_config, temp_helios_dir):
        """Test get_active_persona with existing persona."""
        # Create persona file
        persona_path = temp_helios_dir / "personas"
        persona_path.mkdir(parents=True, exist_ok=True)
        
        with open(persona_path / "test_persona.yaml", "w") as f:
            yaml.safe_dump(sample_persona_config, f)
        
        result = await test_client.call_tool("get_active_persona", persona_name="test_persona")
        
        assert result["status"] == "success"
        assert result["persona"]["specialization_level"] == sample_persona_config["specialization_level"]
    
    @pytest.mark.asyncio
    async def test_merge_behaviors_calculation(self, test_client):
        """Test merge_behaviors tool calculates inheritance correctly."""
        result = await test_client.call_tool("merge_behaviors", persona_name="test")
        
        assert result["status"] == "success"
        assert "calculation" in result
        
        calc = result["calculation"]
        assert "base_importance" in calc
        assert "specialization_level" in calc
        assert "inheritance_weight" in calc
        assert "persona_weight" in calc
        
        # Verify the core formula
        expected_weight = calc["base_importance"] / (calc["specialization_level"] ** 2)
        assert abs(calc["inheritance_weight"] - expected_weight) < 0.001
        
        # Weights should sum to 1
        assert abs(calc["inheritance_weight"] + calc["persona_weight"] - 1.0) < 0.001
    
    @pytest.mark.asyncio
    async def test_list_personas_empty(self, test_client):
        """Test list_personas with no personas."""
        result = await test_client.call_tool("list_personas")
        
        assert result["status"] == "success"
        assert "personas" in result
        assert isinstance(result["personas"], list)
        assert result["count"] == len(result["personas"])
    
    @pytest.mark.asyncio
    async def test_list_personas_with_data(self, test_client, temp_helios_dir, sample_persona_config):
        """Test list_personas with existing personas."""
        # Create test personas
        persona_path = temp_helios_dir / "personas"
        persona_path.mkdir(parents=True, exist_ok=True)
        
        for name in ["developer", "researcher", "analyst"]:
            with open(persona_path / f"{name}.yaml", "w") as f:
                yaml.safe_dump(sample_persona_config, f)
        
        result = await test_client.call_tool("list_personas")
        
        assert result["status"] == "success"
        assert len(result["personas"]) == 3
        assert "developer" in result["personas"]
        assert "researcher" in result["personas"]
        assert "analyst" in result["personas"]
    
    @pytest.mark.asyncio
    async def test_update_preference_simple(self, test_client, temp_helios_dir):
        """Test update_preference tool."""
        result = await test_client.call_tool(
            "update_preference",
            domain="technical",
            key="language",
            value="python"
        )
        
        assert result["status"] == "success"
        assert result["updated"]["domain"] == "technical"
        assert result["updated"]["key"] == "language"
        assert result["updated"]["value"] == "python"
    
    @pytest.mark.asyncio
    async def test_search_patterns_empty(self, test_client):
        """Test search_patterns with no patterns."""
        result = await test_client.call_tool("search_patterns", query="test")
        
        assert result["status"] == "success"
        assert "patterns" in result
        assert len(result["patterns"]) == 0
        assert result["total_found"] == 0


class TestConfigurationLoading:
    """Test configuration loading and persistence."""
    
    @pytest.mark.asyncio
    async def test_config_loader_yaml_operations(self, config_loader, temp_helios_dir):
        """Test YAML loading and saving operations."""
        test_data = {
            "test_key": "test_value",
            "nested": {
                "value": 42,
                "list": [1, 2, 3]
            }
        }
        
        test_file = temp_helios_dir / "test_config.yaml"
        
        # Save data
        await config_loader.save_yaml(test_file, test_data)
        assert test_file.exists()
        
        # Load data back
        loaded_data = await config_loader.load_yaml(test_file)
        assert loaded_data == test_data
    
    @pytest.mark.asyncio
    async def test_config_loader_missing_file(self, config_loader, temp_helios_dir):
        """Test loading non-existent file."""
        missing_file = temp_helios_dir / "missing.yaml"
        
        with pytest.raises(FileNotFoundError):
            await config_loader.load_yaml(missing_file)
    
    @pytest.mark.asyncio
    async def test_load_base_config_creates_default(self, config_loader):
        """Test that load_base_config creates default when missing."""
        config = await config_loader.load_base_config()
        
        assert "base_importance" in config
        assert "behaviors" in config
        assert "identity" in config
        assert config["version"] == "1.0.0"
        
        # Should have created the identity.yaml file
        identity_file = config_loader.config.base_path / "identity.yaml"
        assert identity_file.exists()


class TestGitPersistence:
    """Test git persistence functionality."""
    
    def test_git_store_initialization(self, temp_helios_dir):
        """Test GitStore initialization."""
        with patch('helios_mcp.git_store.Repo') as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            
            store = GitStore(temp_helios_dir)
            assert store.helios_dir == temp_helios_dir
            assert store.repo == mock_repo
    
    def test_auto_commit_no_changes(self, git_store, mock_git_repo):
        """Test auto_commit with no changes."""
        mock_git_repo.is_dirty.return_value = False
        mock_git_repo.untracked_files = []
        
        result = git_store.auto_commit("test commit")
        assert result is False  # No changes to commit
    
    def test_auto_commit_with_changes(self, git_store, mock_git_repo):
        """Test auto_commit with changes."""
        mock_git_repo.is_dirty.return_value = True
        mock_git_repo.untracked_files = ["new_file.yaml"]
        
        result = git_store.auto_commit("test commit")
        assert result is True
        mock_git_repo.git.add.assert_called_with(A=True)
        mock_git_repo.index.commit.assert_called_once()
    
    def test_get_repo_status(self, git_store, mock_git_repo):
        """Test repository status reporting."""
        mock_git_repo.is_dirty.return_value = True
        mock_git_repo.untracked_files = ["untracked.yaml"]
        
        status = git_store.get_repo_status()
        
        assert status["is_dirty"] is True
        assert "untracked.yaml" in status["untracked_files"]
        assert status["clean"] is False


class TestErrorHandling:
    """Test error handling across server components."""
    
    @pytest.mark.asyncio
    async def test_tool_error_handling(self, temp_helios_dir):
        """Test that tool errors are handled gracefully."""
        from tests.conftest import MockTestClient
        
        server = create_server(temp_helios_dir)
        client = MockTestClient(server)
        
        # Test with invalid inputs that might cause errors
        result = await client.call_tool("get_active_persona", persona_name="")
        
        # Should not crash, should return error status
        assert "status" in result
        if result["status"] == "error":
            assert "message" in result
    
    def test_inheritance_calculator_edge_cases(self):
        """Test inheritance calculator with edge cases."""
        calculator = InheritanceCalculator()
        
        # Test with boundary values
        weight = calculator.calculate_weight(base_importance=0.0, specialization_level=1)
        assert weight >= 0.01  # Should be clamped to minimum
        
        weight = calculator.calculate_weight(base_importance=1.0, specialization_level=1)
        assert weight <= 0.99  # Should be clamped to maximum