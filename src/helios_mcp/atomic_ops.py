"""Durable writes: atomic file replacement and git commits of profile history."""

import logging
import os
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


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


_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "helios",
    "GIT_AUTHOR_EMAIL": "helios@localhost",
    "GIT_COMMITTER_NAME": "helios",
    "GIT_COMMITTER_EMAIL": "helios@localhost",
}

_GITIGNORE = """\
# Derived or high-churn state; profiles and proposals are the history.
observations/
rendered/
temporary/
*.lock
*.tmp
"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    has_identity = subprocess.run(
        ["git", "-C", str(repo), "config", "user.email"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if not has_identity:
        env.update(_GIT_IDENTITY)
    # Signing can prompt for a passphrase, and this runs from hooks and the MCP
    # server where nobody can answer.
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=False, env=env,
    )


def git_commit(repo: Path, paths: Iterable[Path], message: str) -> str | None:
    """Commit ``paths`` in ``repo``, initializing it if needed.

    Returns the new commit sha, or None when git is unavailable, nothing
    changed, or the commit failed. Profile writes must not fail because
    history could not be recorded, so failures are logged, not raised.
    """
    try:
        if not (repo / ".git").exists():
            repo.mkdir(parents=True, exist_ok=True)
            if _git(repo, "init", "-q").returncode != 0:
                return None
            gitignore = repo / ".gitignore"
            if not gitignore.exists():
                atomic_write_text(gitignore, _GITIGNORE)
            paths = [*paths, gitignore]
        rel = [str(Path(p).resolve().relative_to(repo.resolve())) for p in paths]
        _git(repo, "add", "--", *rel)
        if _git(repo, "diff", "--cached", "--quiet").returncode == 0:
            return None
        result = _git(repo, "commit", "-q", "-m", message)
        if result.returncode != 0:
            logger.warning("git commit in %s failed: %s", repo, result.stderr.strip())
            return None
        return _git(repo, "rev-parse", "HEAD").stdout.strip() or None
    except (OSError, ValueError) as exc:
        logger.warning("git commit in %s failed: %s", repo, exc)
        return None
