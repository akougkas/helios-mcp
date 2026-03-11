"""Helios MCP — behavioral science for AI agents."""

from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

try:
    from importlib.metadata import version
except ImportError:
    version = None  # type: ignore[assignment]


def _get_version() -> str:
    try:
        if tomllib is not None:
            pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
            if pyproject.exists():
                with pyproject.open("rb") as f:
                    v = tomllib.load(f)["project"]["version"]
                    if isinstance(v, str) and v:
                        return v
    except Exception:
        pass
    try:
        if version is not None:
            return version("helios-mcp")
    except Exception:
        pass
    return "0.4.0b1"


__version__ = _get_version()
