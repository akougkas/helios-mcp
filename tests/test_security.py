"""Persona name and path validation: the boundary that keeps writes inside
HELIOS_DIR. Every case here is a concrete attack a persona_name argument
from an untrusted MCP caller could carry."""

import pytest

from helios_mcp.security import (
    InvalidInputError,
    PathTraversalError,
    persona_path,
    validate_persona_name,
)


class TestValidatePersonaName:
    @pytest.mark.parametrize(
        "name", ["developer", "dev_user", "coder-1", "A", "a" * 50]
    )
    def test_accepts_whitelisted_names(self, name):
        assert validate_persona_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "../../x",
            "..",
            ".",
            "../etc/passwd",
            "a/b",
            "a\\b",
            "",
            "   ",
            " developer",
            "developer ",
            "a" * 51,
            "dev.user",
            "dev/../user",
            "~root",
            "dev\0user",
        ],
    )
    def test_rejects_traversal_and_unsafe_names(self, name):
        with pytest.raises(InvalidInputError):
            validate_persona_name(name)

    def test_rejects_non_string(self):
        with pytest.raises(InvalidInputError):
            validate_persona_name(None)  # type: ignore[arg-type]


class TestPersonaPath:
    def test_stays_under_base_dir(self, tmp_path):
        base = tmp_path / "personas"
        base.mkdir()
        result = persona_path(base, "developer", ".yaml")
        assert result == (base / "developer.yaml").resolve()
        assert result.is_relative_to(base.resolve())

    def test_supports_multi_part_suffix(self, tmp_path):
        base = tmp_path / "personas"
        base.mkdir()
        result = persona_path(base, "developer", "_user.yaml")
        assert result.name == "developer_user.yaml"

    def test_rejects_traversal_in_persona(self, tmp_path):
        base = tmp_path / "personas"
        base.mkdir()
        with pytest.raises(InvalidInputError):
            persona_path(base, "../../etc/passwd", ".json")

    def test_rejects_traversal_in_suffix(self, tmp_path):
        base = tmp_path / "personas"
        base.mkdir()
        with pytest.raises(InvalidInputError):
            persona_path(base, "developer", "/../../evil.yaml")

    def test_base_dir_need_not_exist_yet(self, tmp_path):
        base = tmp_path / "not-yet-created"
        result = persona_path(base, "developer", ".yaml")
        assert result.is_relative_to(base.resolve())

    def test_symlinked_base_dir_still_contains_result(self, tmp_path):
        real_base = tmp_path / "real"
        real_base.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real_base)
        result = persona_path(link, "developer", ".yaml")
        assert result.is_relative_to(real_base.resolve())

    def test_escape_is_unreachable_but_would_raise_path_traversal(self, tmp_path):
        # validate_persona_name already blocks every case that could make
        # persona_path escape base_dir, so this documents the second,
        # independent guarantee (resolve + relative_to) rather than
        # exercising a live bypass.
        base = tmp_path / "personas"
        base.mkdir()
        with pytest.raises((InvalidInputError, PathTraversalError)):
            persona_path(base, "..", ".yaml")
