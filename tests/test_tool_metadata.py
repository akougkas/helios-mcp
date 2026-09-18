"""Structured-output and annotation metadata tests for the 7 MCP tools.

These tests introspect the FastMCP server object returned by
``create_server()`` directly (via ``get_tools()``) rather than invoking the
tools, so they assert on the published MCP tool contract: registration,
behavior hints (readOnlyHint/destructiveHint/idempotentHint), and the
presence of a non-empty structured output schema.
"""

from pathlib import Path

import pytest

from helios_mcp.server import create_server

EXPECTED_HINTS = {
    "list_personas": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    "get_behavioral_context": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    "observe_interaction": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    },
    "get_drift_report": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    "negotiate_update": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
    },
    "import_profile": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
    },
    "export_profile": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
}


@pytest.fixture
async def registered_tools(temp_helios_dir: Path) -> dict:
    """Return the {name: Tool} mapping registered on a fresh Helios server."""
    mcp = await create_server(temp_helios_dir)
    return await mcp.get_tools()


async def test_all_seven_tools_are_registered(registered_tools: dict) -> None:
    assert set(EXPECTED_HINTS) == set(registered_tools)


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_HINTS))
async def test_tool_has_expected_behavior_hints(
    registered_tools: dict, tool_name: str
) -> None:
    tool = registered_tools[tool_name]
    expected = EXPECTED_HINTS[tool_name]

    assert tool.annotations is not None, f"{tool_name} has no annotations"
    assert tool.annotations.readOnlyHint is expected["readOnlyHint"]
    assert tool.annotations.destructiveHint is expected["destructiveHint"]
    assert tool.annotations.idempotentHint is expected["idempotentHint"]
    assert tool.annotations.title, f"{tool_name} has no human-readable title"


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_HINTS))
async def test_tool_publishes_non_empty_output_schema(
    registered_tools: dict, tool_name: str
) -> None:
    tool = registered_tools[tool_name]

    assert tool.output_schema, f"{tool_name} has no output schema"
    assert tool.output_schema.get("type") == "object"
    assert tool.output_schema.get("properties"), (
        f"{tool_name} output schema has no properties"
    )


async def test_list_personas_is_open_world_false(registered_tools: dict) -> None:
    """list_personas is scoped to the local Helios directory, not the open web."""
    assert registered_tools["list_personas"].annotations.openWorldHint is False
