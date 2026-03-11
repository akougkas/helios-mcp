"""Configuration management for Helios MCP server."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from .atomic_ops import atomic_write_yaml

logger = logging.getLogger(__name__)


@dataclass
class HeliosConfig:
    """Helios directory layout."""

    base_path: Path
    personas_path: Path
    learned_path: Path
    temporary_path: Path

    @classmethod
    def default(cls) -> "HeliosConfig":
        base = Path.home() / ".helios"
        return cls(
            base_path=base / "base",
            personas_path=base / "personas",
            learned_path=base / "learned",
            temporary_path=base / "temporary",
        )

    def ensure_directories(self) -> None:
        for p in [self.base_path, self.personas_path, self.learned_path, self.temporary_path]:
            p.mkdir(parents=True, exist_ok=True)


class ConfigLoader:
    """Loads and saves YAML configuration files."""

    def __init__(self, config: HeliosConfig) -> None:
        self.config = config
        self.config.ensure_directories()

    async def load_yaml(self, file_path: Path) -> Dict[str, Any]:
        with file_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    async def save_yaml(self, file_path: Path, data: Dict[str, Any]) -> None:
        atomic_write_yaml(file_path, data)

    async def load_base_config(self) -> Dict[str, Any]:
        identity = self.config.base_path / "identity.yaml"
        if identity.exists():
            return await self.load_yaml(identity)
        config_file = self.config.base_path / "config.yaml"
        return await self.load_yaml(config_file)

    async def load_persona_config(self, name: str) -> Optional[Dict[str, Any]]:
        path = self.config.personas_path / f"{name}.yaml"
        try:
            return await self.load_yaml(path)
        except FileNotFoundError:
            return None

    async def list_personas(self) -> list[str]:
        return [f.stem for f in self.config.personas_path.glob("*.yaml")]
