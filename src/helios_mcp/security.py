"""Path and input validation for Helios MCP.

Every persona-derived filesystem write goes through validate_persona_name
and persona_path. Both are whitelist-based: a name is accepted only if it
matches a narrow character class, not rejected because it matches a
blocklist of known-bad patterns.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


SAFE_PERSONA_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")
SAFE_SUFFIX_PATTERN = re.compile(r"^[a-zA-Z0-9_.]{1,50}$")


class SecurityError(Exception):
    """Base exception for security violations."""


class PathTraversalError(SecurityError):
    """Raised when a resolved path would escape its base directory."""


class InvalidInputError(SecurityError):
    """Raised when input fails whitelist validation."""


def validate_persona_name(name: str) -> str:
    """Validate a persona name against a strict whitelist.

    Only ASCII letters, digits, underscore and hyphen are accepted, 1-50
    characters, with no leading/trailing whitespace. The pattern excludes
    "." entirely, which also rules out "." and ".." as a side effect, and
    excludes "/" and "\\", so a validated name cannot address a path
    outside a single directory component.

    Raises:
        InvalidInputError: If name is empty, not a string, too long, or
            contains any character outside the whitelist.
    """
    if not isinstance(name, str) or not name:
        raise InvalidInputError("Persona name must be a non-empty string")

    if name != name.strip():
        raise InvalidInputError(
            f"Persona name must not have leading or trailing whitespace: {name!r}"
        )

    if not SAFE_PERSONA_NAME_PATTERN.match(name):
        raise InvalidInputError(
            "Persona name contains invalid characters. Only alphanumeric, "
            f"underscore, and hyphen allowed (max 50 chars): {name!r}"
        )

    return name


def persona_path(base_dir: Path, persona: str, suffix: str) -> Path:
    """Build base_dir/{persona}{suffix}, guaranteed to resolve under base_dir.

    Validates persona through validate_persona_name and suffix against a
    matching whitelist (letters, digits, underscore, and dot; no path
    separators), so callers get one call for both "is this name safe"
    and "is this path safe" instead of relying on validate_persona_name
    having already run. The resolved path is re-checked against base_dir as
    a second, independent guarantee: even if the whitelist regexes above
    were ever loosened, a traversal attempt would still be caught here.

    Raises:
        InvalidInputError: If persona or suffix fails whitelist validation.
        PathTraversalError: If the resulting path would not stay under
            base_dir (defense in depth; unreachable if the whitelists hold).
    """
    validated_persona = validate_persona_name(persona)

    if not SAFE_SUFFIX_PATTERN.match(suffix):
        raise InvalidInputError(
            "Suffix contains invalid characters. Only alphanumeric, "
            f"underscore, and dot allowed (max 50 chars): {suffix!r}"
        )

    resolved_base = base_dir.resolve()
    candidate = (base_dir / f"{validated_persona}{suffix}").resolve()

    try:
        candidate.relative_to(resolved_base)
    except ValueError as e:
        raise PathTraversalError(
            f"Resolved path {candidate} escapes base directory {resolved_base}"
        ) from e

    return candidate


def sanitize_error_message(error: Exception) -> str:
    """Sanitize error message for safe display to users.

    Args:
        error: Exception to sanitize

    Returns:
        Sanitized error message
    """
    error_str = str(error)

    # Remove potentially sensitive information
    # Replace Unix full paths with just filenames
    error_str = re.sub(r"/[^\s]*/", ".../", error_str)
    # Replace Windows full paths (C:\Users\... or \\server\share\...)
    error_str = re.sub(r"[A-Za-z]:\\[^\s]*", "[PATH]", error_str)
    error_str = re.sub(r"\\\\[^\s]+", "[PATH]", error_str)

    # Limit length
    if len(error_str) > 200:
        error_str = error_str[:197] + "..."

    return error_str
