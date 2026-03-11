"""Shared fixtures for Helios MCP tests."""

import pytest
import tempfile
from pathlib import Path

from helios_mcp.config import HeliosConfig


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
        temporary_path=temp_helios_dir / "temporary",
    )
