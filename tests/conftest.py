"""Shared fixtures for Helios MCP tests."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil
import yaml

from helios_mcp.server import create_server
from helios_mcp.config import HeliosConfig, ConfigLoader
from helios_mcp.inheritance import InheritanceCalculator, BehaviorMerger
from helios_mcp.git_store import GitStore


class MockTestClient:
    """Mock test client for MCP server testing."""
    
    def __init__(self, server):
        self.server = server
        
    async def call_tool(self, tool_name, **kwargs):
        """Call a tool function directly."""
        if hasattr(self.server, '_tools') and tool_name in self.server._tools:
            tool = self.server._tools[tool_name]
            func = tool.func if hasattr(tool, 'func') else tool
            return await func(**kwargs)
        else:
            # Fallback to getting tools from the server's module
            import helios_mcp.server as server_module
            
            # Get the actual functions from the decorated tools
            if hasattr(server_module, 'mcp') and hasattr(server_module.mcp, '_tools'):
                tools = server_module.mcp._tools
                if tool_name in tools:
                    func = tools[tool_name].func
                    return await func(**kwargs)
                    
            raise ValueError(f"Tool {tool_name} not found")


@pytest.fixture
def temp_helios_dir():
    """Create temporary Helios directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        helios_path = Path(tmpdir) / ".helios"
        helios_path.mkdir()
        yield helios_path


@pytest.fixture
def helios_config(temp_helios_dir):
    """Create HeliosConfig with temporary directory."""
    return HeliosConfig(
        base_path=temp_helios_dir / "base",
        personas_path=temp_helios_dir / "personas", 
        learned_path=temp_helios_dir / "learned",
        temporary_path=temp_helios_dir / "temporary"
    )


@pytest.fixture
def config_loader(helios_config):
    """Create ConfigLoader with test configuration."""
    return ConfigLoader(helios_config)


@pytest.fixture
def sample_base_config():
    """Sample base configuration for testing."""
    return {
        "base_importance": 0.7,
        "behaviors": {
            "communication_style": "technical",
            "response_format": "structured",
            "detail_level": "comprehensive"
        },
        "preferences": {
            "tools": ["python", "rust"],
            "methodology": "incremental"
        },
        "version": "1.0.0"
    }


@pytest.fixture
def sample_persona_config():
    """Sample persona configuration for testing."""
    return {
        "specialization_level": 2,
        "behaviors": {
            "communication_style": "casual",
            "domain_focus": "web_development",
            "response_length": "concise"
        },
        "preferences": {
            "frameworks": ["fastapi", "react"],
            "testing": "jest"
        },
        "learning_rate": 0.1,
        "version": "1.0"
    }


@pytest.fixture
def inheritance_calculator():
    """Create InheritanceCalculator for testing."""
    return InheritanceCalculator()


@pytest.fixture
def behavior_merger():
    """Create BehaviorMerger for testing."""
    return BehaviorMerger()


@pytest.fixture
def mock_git_repo():
    """Mock git repository for testing."""
    mock_repo = Mock()
    mock_repo.is_dirty.return_value = False
    mock_repo.untracked_files = []
    mock_repo.heads = True
    mock_repo.git.add = Mock()
    mock_repo.index.commit = Mock()
    return mock_repo


@pytest.fixture
def git_store(temp_helios_dir, mock_git_repo):
    """Create GitStore with mocked repository."""
    with patch('helios_mcp.git_store.Repo') as mock_repo_class:
        mock_repo_class.return_value = mock_git_repo
        store = GitStore(temp_helios_dir)
        yield store


@pytest.fixture
async def test_server(temp_helios_dir, sample_base_config):
    """Create test MCP server with sample data."""
    # Set up sample configuration
    base_path = temp_helios_dir / "base"
    base_path.mkdir(parents=True, exist_ok=True)
    
    # Create base config file
    with open(base_path / "identity.yaml", "w") as f:
        yaml.safe_dump(sample_base_config, f)
    
    # Create server
    server = create_server(temp_helios_dir)
    return server


@pytest.fixture
def test_client(test_server):
    """Create test client for MCP server."""
    return MockTestClient(test_server)


@pytest.fixture 
def cli_runner():
    """Create Click CLI runner for testing."""
    from click.testing import CliRunner
    return CliRunner()