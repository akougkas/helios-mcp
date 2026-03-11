"""Atomic file operations for safe YAML handling."""

import os
import tempfile
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def atomic_write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Write YAML atomically via temp file + rename.

    Args:
        path: Target YAML file path.
        data: Data to serialize as YAML.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        suffix=".tmp", prefix=f"{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        Path(temp_name).replace(path)
    except Exception:
        os.unlink(temp_name)
        raise


def validate_yaml_file(path: Path) -> bool:
    """Check that a YAML file exists and parses without error."""
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            yaml.safe_load(f)
        return True
    except (yaml.YAMLError, OSError):
        return False
