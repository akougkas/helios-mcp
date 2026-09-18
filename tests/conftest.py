"""Shared fixtures for Helios MCP tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_helios_dir():
    """Create temporary Helios directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        helios_path = Path(tmpdir) / ".helios"
        helios_path.mkdir()
        yield helios_path


@pytest.fixture(autouse=True)
def _no_model_calls(monkeypatch):
    """Tests never spawn the model CLI; tests that exercise it inject a fake client."""
    monkeypatch.setenv("HELIOS_LLM", "0")
