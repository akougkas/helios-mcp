"""First-run setup of HELIOS_DIR: layout, default profiles, and the initial commit."""

import datetime
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .atomic_ops import atomic_write_yaml, git_commit

logger = logging.getLogger(__name__)

_DEFAULT_PROFILES = Path(__file__).parent / "default_profiles"
DOMAIN_PERSONAS = ("developer", "researcher", "writer")


class BootstrapManager:
    """Creates a fresh installation and tracks boots in ``.helios_version``."""

    def __init__(self, helios_dir: Path, git_enabled: bool = True) -> None:
        self.helios_dir = helios_dir
        self.git_enabled = git_enabled
        self.version_file = helios_dir / ".helios_version"

    def is_first_install(self) -> bool:
        return not self.version_file.exists()

    def bootstrap_installation(self) -> None:
        """Create the layout and default profiles, then commit them.

        The version file is written last, so a failed bootstrap is retried on
        the next start.
        """
        for sub in ("base", "personas", "temporary"):
            (self.helios_dir / sub).mkdir(parents=True, exist_ok=True)
        written = self._install_default_profiles()
        if self.git_enabled:
            git_commit(self.helios_dir, written, "Initial behavioral profiles")
        now = datetime.datetime.now().isoformat()
        atomic_write_yaml(self.version_file, {
            "version": __version__,
            "install_date": now,
            "last_boot": now,
            "git_enabled": self.git_enabled,
        })
        logger.info("Helios installation bootstrap complete")

    def get_installation_info(self) -> dict[str, Any]:
        if not self.version_file.exists():
            return {"installed": False, "version": None, "install_date": None}
        try:
            info = yaml.safe_load(self.version_file.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as e:
            logger.warning(f"Failed to read installation info: {e}")
            return {"installed": True, "version": "unknown", "error": str(e)}
        return {
            "installed": True,
            "version": info.get("version", "unknown"),
            "install_date": info.get("install_date"),
            "last_boot": info.get("last_boot"),
        }

    def update_last_boot(self) -> None:
        info = self.get_installation_info()
        if not info["installed"]:
            return
        try:
            atomic_write_yaml(self.version_file, {
                "version": info.get("version", __version__),
                "install_date": info.get("install_date"),
                "last_boot": datetime.datetime.now().isoformat(),
            })
        except OSError as e:
            logger.warning(f"Failed to update last boot timestamp: {e}")

    def _install_default_profiles(self) -> list[Path]:
        """Copy default profiles that are absent. Never overwrites user edits."""
        pairs = [(_DEFAULT_PROFILES / "identity.yaml",
                  self.helios_dir / "base" / "identity.yaml")]
        pairs += [(_DEFAULT_PROFILES / f"{name}.yaml",
                   self.helios_dir / "personas" / f"{name}.yaml")
                  for name in DOMAIN_PERSONAS]
        written = []
        for src, dst in pairs:
            if not dst.exists():
                shutil.copy2(src, dst)
                written.append(dst)
        return written
