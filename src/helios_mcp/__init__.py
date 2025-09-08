"""Helios MCP - Configuration management for AI behaviors with weighted inheritance."""

import os
from pathlib import Path
from typing import Optional

from .config import HeliosConfig, ConfigLoader
from .server import create_server


def _get_version() -> str:
    """Get version dynamically from pyproject.toml or fallback."""
    try:
        # Try to read from pyproject.toml if available
        import tomllib
        project_root = Path(__file__).parent.parent.parent
        pyproject_path = project_root / "pyproject.toml"
        
        if pyproject_path.exists():
            with pyproject_path.open("rb") as f:
                pyproject = tomllib.load(f)
                return pyproject["project"]["version"]
    except (ImportError, FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
        pass
    
    # Fallback to package metadata if installed
    try:
        from importlib.metadata import version
        return version("helios-mcp")
    except ImportError:
        pass
    
    # Final fallback
    return "0.3.0"


__version__ = _get_version()
__all__ = ["HeliosConfig", "ConfigLoader", "create_server"]