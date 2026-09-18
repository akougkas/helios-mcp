"""Helios MCP server: seven tools, each a thin layer over HeliosService.

Every tool returns ``status`` plus either the service payload or ``message``.
Result TypedDicts are total=False because the error branch carries only
``status`` and ``message``.
"""

import logging
from pathlib import Path
from typing import Any, TypedDict, cast

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .security import sanitize_error_message
from .service import DimensionReport, HeliosService

logger = logging.getLogger(__name__)

_PERSONA_HELP = (
    "Persona name, e.g. 'developer'. Omit to use HELIOS_DIR/default_persona, "
    "or 'default' when that is unset."
)


class ListPersonasResult(TypedDict, total=False):
    status: str
    personas: list[str]
    message: str


class GetBehavioralContextResult(TypedDict, total=False):
    status: str
    persona: str
    behavioral_context: str
    observation_count: int
    specialization_level: int
    message: str


class ObserveInteractionResult(TypedDict, total=False):
    status: str
    persona: str
    observations_added: int
    turns: int
    negotiation_recommended: bool
    proposal_id: str | None
    proposal_tier: str | None
    auto_accepted: list[str]
    message: str


class GetDriftReportResult(TypedDict, total=False):
    status: str
    persona: str
    turns: int
    negotiation_recommended: bool
    proposal_id: str | None
    proposal_tier: str | None
    summary: str
    per_dimension: dict[str, str]
    endorsed: dict[str, DimensionReport]
    fingerprint: dict[str, DimensionReport]
    auto_accepted: list[str]
    cooling_down: list[str]
    message: str


class NegotiateUpdateResult(TypedDict, total=False):
    status: str
    persona: str
    proposal_id: str
    decision: str
    dimensions: list[str]
    commit: str | None
    reason: str | None
    message: str


class ImportProfileResult(TypedDict, total=False):
    status: str
    persona: str
    source: str
    saved_to: str
    commit: str | None
    distributions: dict[str, dict[str, str | float]]
    message: str


class ExportProfileResult(TypedDict, total=False):
    status: str
    persona: str
    format: str
    content: str
    agent_id: str
    level: str
    dimensions: dict[str, dict[str, Any]]
    message: str


def _error(tool: str, exc: Exception) -> Any:
    logger.error("%s failed: %s", tool, exc)
    return {"status": "error", "message": sanitize_error_message(exc)}


def _ok(payload: Any) -> Any:
    return {"status": "success", **payload}


async def create_server(helios_dir: Path | None = None) -> FastMCP:
    """Create the Helios MCP server over ``helios_dir`` (default ``~/.helios``)."""
    if helios_dir is None:
        helios_dir = Path.home() / ".helios"
    helios_dir.mkdir(parents=True, exist_ok=True)
    service = HeliosService(helios_dir)
    mcp = FastMCP("Helios")

    @mcp.tool(
        description="List available persona names in the Helios directory",
        tags={"personas"},
        title="List Personas",
        annotations=ToolAnnotations(
            title="List Personas", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    async def list_personas(
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ListPersonasResult:
        try:
            return {"status": "success", "personas": service.list_personas()}
        except Exception as e:
            return cast(ListPersonasResult, _error("list_personas", e))

    @mcp.tool(
        description="Get the behavioral context for a persona as system prompt text",
        tags={"behavioral", "context"},
        title="Get Behavioral Context",
        annotations=ToolAnnotations(
            title="Get Behavioral Context", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True,
        ),
    )
    async def get_behavioral_context(
        persona_name: str = Field(default="", description=_PERSONA_HELP),
        model: str = Field(
            default="",
            description="Model id of the calling agent, e.g. claude-opus-5. When "
            "given, the context counters that model's own observed tendencies; "
            "otherwise it covers the most observed models"),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> GetBehavioralContextResult:
        try:
            return cast(GetBehavioralContextResult,
                        _ok(service.context(persona_name or None, model or None)))
        except Exception as e:
            return cast(GetBehavioralContextResult,
                        _error("get_behavioral_context", e))

    @mcp.tool(
        description="Record the agent turns in a conversation for a persona and "
        "report whether a profile update is recommended",
        tags={"behavioral", "observation"},
        title="Observe Interaction",
        annotations=ToolAnnotations(
            title="Observe Interaction", readOnlyHint=False,
            destructiveHint=False, idempotentHint=False,
        ),
    )
    async def observe_interaction(
        messages: list[dict[str, Any]] = Field(
            description="Conversation messages (role+content dicts). An "
            "assistant turn is recorded once a user message follows it, so "
            "re-send the growing conversation with the same session_id"
        ),
        persona_name: str = Field(default="", description=_PERSONA_HELP),
        session_id: str = Field(
            default="",
            description="Stable id for this conversation, so repeated calls "
            "do not count the same turns twice",
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ObserveInteractionResult:
        try:
            return cast(ObserveInteractionResult, _ok(service.observe_messages(
                persona_name or None, messages, session_id or None)))
        except Exception as e:
            return cast(ObserveInteractionResult, _error("observe_interaction", e))

    @mcp.tool(
        description="Get the drift report for a persona: endorsed drift, "
        "fingerprint diagnostics and the id of the pending proposal, if any. "
        "Call when negotiation_recommended is true.",
        tags={"behavioral", "drift"},
        title="Get Drift Report",
        annotations=ToolAnnotations(
            # Persists the pending proposal so its id stays valid, which is a
            # write, but never changes a profile; repeated calls on the same
            # ledger return the same proposal.
            title="Get Drift Report", readOnlyHint=False,
            destructiveHint=False, idempotentHint=True,
        ),
    )
    async def get_drift_report(
        persona_name: str = Field(default="", description=_PERSONA_HELP),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> GetDriftReportResult:
        try:
            return cast(GetDriftReportResult,
                        _ok(service.drift_report(persona_name or None)))
        except Exception as e:
            return cast(GetDriftReportResult, _error("get_drift_report", e))

    @mcp.tool(
        description="Accept or reject a proposal from get_drift_report. Accepted "
        "changes update the persona's user profile and are git-committed; "
        "rejections are recorded and pause proposals on those dimensions.",
        tags={"behavioral", "negotiation"},
        title="Negotiate Behavioral Update",
        annotations=ToolAnnotations(
            # Accept overwrites the persona's user-level distributions.
            title="Negotiate Behavioral Update", readOnlyHint=False,
            destructiveHint=True, idempotentHint=False,
        ),
    )
    async def negotiate_update(
        proposal_id: str = Field(description="Proposal id from get_drift_report"),
        decision: str = Field(description="'accept' or 'reject'"),
        persona_name: str = Field(default="", description=_PERSONA_HELP),
        reason: str = Field(default="", description="Why, for a rejection"),
        accepted_dimensions: list[str] | None = Field(
            default=None,
            description="Dimensions to decide on (default: all in the proposal)",
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> NegotiateUpdateResult:
        try:
            choice = decision.strip().lower()
            persona = persona_name or None
            if choice == "accept":
                report = service.accept(persona, proposal_id, accepted_dimensions)
            elif choice == "reject":
                report = service.reject(persona, proposal_id, reason,
                                        accepted_dimensions)
            else:
                raise ValueError(
                    f"unknown decision {decision!r}; use 'accept' or 'reject'")
            return {
                "status": "success",
                "persona": report["persona"],
                "proposal_id": report["proposal_id"],
                "decision": report["status"],
                "dimensions": report["dimensions"],
                "commit": report["commit"],
                "reason": report["reason"],
            }
        except Exception as e:
            return cast(NegotiateUpdateResult, _error("negotiate_update", e))

    @mcp.tool(
        description="Import a personality file (CLAUDE.md, soul.md, etc.) into "
        "a Helios behavioral profile",
        tags={"behavioral", "import"},
        title="Import Profile",
        annotations=ToolAnnotations(
            # Overwrites an existing persona file of the same name; the
            # previous version stays in HELIOS_DIR's git history.
            title="Import Profile", readOnlyHint=False,
            destructiveHint=True, idempotentHint=False,
        ),
    )
    async def import_profile(
        source_path: str = Field(description="Path to the personality file to import"),
        persona_name: str = Field(
            default="",
            description="Name for the new persona (default: derived from filename)",
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ImportProfileResult:
        try:
            path = Path(source_path).expanduser().resolve()
            return cast(ImportProfileResult,
                        _ok(service.import_profile(path, persona_name or None)))
        except Exception as e:
            return cast(ImportProfileResult, _error("import_profile", e))

    @mcp.tool(
        description="Export a behavioral profile in various formats "
        "(yaml, json, soulspec)",
        tags={"behavioral", "export"},
        title="Export Profile",
        annotations=ToolAnnotations(
            title="Export Profile", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True,
        ),
    )
    async def export_profile(
        persona_name: str = Field(default="", description=_PERSONA_HELP),
        format: str = Field(  # noqa: A002 - published MCP export-format parameter name
            default="yaml", description="Export format: yaml, json, or soulspec"
        ),
        dimensions: list[str] | None = Field(
            default=None,
            description="Specific dimensions to include (None = all)",
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ExportProfileResult:
        try:
            return cast(ExportProfileResult, _ok(service.export_profile(
                persona_name or None, format, dimensions)))
        except Exception as e:
            return cast(ExportProfileResult, _error("export_profile", e))

    logger.info("Helios MCP server created (config: %s)", helios_dir)
    return mcp
