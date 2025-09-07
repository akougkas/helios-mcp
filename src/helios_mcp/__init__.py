"""Helios MCP - Configuration management for AI behaviors with weighted inheritance."""

from .config import HeliosConfig, ConfigLoader
from .server import main

__version__ = "0.1.0"
__all__ = ["HeliosConfig", "ConfigLoader", "main"]