"""Atomic file writes: temp file in the target directory, fsync, then rename."""

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def atomic_write_text(path: Path, text: str) -> None:
    """Write text so readers see either the old file or the new one, never a mix."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        suffix=".tmp", prefix=f"{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        Path(temp_name).replace(path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Serialize ``data`` as YAML and write it atomically."""
    atomic_write_text(
        path,
        yaml.safe_dump(
            data, default_flow_style=False, sort_keys=False, allow_unicode=True
        ),
    )


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
