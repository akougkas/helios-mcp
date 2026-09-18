"""Helios MCP Server — behavioral science tools for AI agents."""

import logging
from pathlib import Path
from typing import Any, TypedDict

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .security import (
    sanitize_error_message,
    validate_persona_name,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output shapes — one TypedDict per tool return payload.
#
# Tools whose bodies only ever return one key set use a total (all-required)
# TypedDict. Tools with an error/short-circuit branch that returns a
# different key set use total=False so every key that can genuinely appear
# on any success/error path is modeled without inventing or renaming keys.
# ---------------------------------------------------------------------------


class ListPersonasResult(TypedDict):
    """Return shape of list_personas — a single, unconditional success shape."""

    status: str
    personas: list[str]


class GetBehavioralContextResult(TypedDict, total=False):
    """Return shape of get_behavioral_context (success or error branch)."""

    status: str
    persona: str
    behavioral_context: str
    observation_count: int
    specialization_level: int
    message: str


class ObserveInteractionResult(TypedDict, total=False):
    """Return shape of observe_interaction (success or error branch)."""

    status: str
    persona: str
    observation_count: int
    current_drift: float
    drift_threshold: float
    negotiation_recommended: bool
    message: str


class GetDriftReportResult(TypedDict, total=False):
    """Return shape of get_drift_report (success, no_data, or error branch)."""

    status: str
    persona: str
    message: str
    summary: str
    per_dimension: dict[str, str]
    total_drift: float
    exceeds_threshold: bool
    proposed_at: str


class NegotiateUpdateResult(TypedDict, total=False):
    """Return shape of negotiate_update.

    Covers all four branches: rejected (status/persona/reason), applied
    (status/updated_dimensions/commit_message), unknown decision
    (status/message), and the exception handler (status/message).
    """

    status: str
    persona: str
    reason: str
    updated_dimensions: list[str]
    commit_message: str
    message: str


class ImportProfileResult(TypedDict, total=False):
    """Return shape of import_profile (success or error branch)."""

    status: str
    persona: str
    source: str
    saved_to: str
    distributions: dict[str, dict[str, str | float]]
    message: str


class ExportProfileResult(TypedDict, total=False):
    """Return shape of export_profile.

    Covers the soulspec branch (status/persona/format/content), the
    yaml/json branch (status/persona/format/agent_id/level/dimensions,
    spread from export_dimensions), and the exception handler
    (status/message).
    """

    status: str
    persona: str
    format: str
    content: str
    agent_id: str
    level: str
    dimensions: dict[str, dict[str, Any]]
    message: str


async def create_server(helios_dir: Path | None = None) -> FastMCP:
    """Create the Helios MCP server with behavioral science tools.

    Args:
        helios_dir: Path to ~/.helios. Defaults to ~/.helios.

    Returns:
        Configured FastMCP server instance.
    """
    if helios_dir is None:
        helios_dir = Path.home() / ".helios"

    helios_dir.mkdir(parents=True, exist_ok=True)

    mcp = FastMCP("Helios")

    # ------------------------------------------------------------------
    # Tool: list_personas
    # ------------------------------------------------------------------

    @mcp.tool(
        description="List available persona names in the Helios directory",
        tags={"personas"},
        title="List Personas",
        annotations=ToolAnnotations(
            title="List Personas",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def list_personas(
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ListPersonasResult:
        """Return the names of all .yaml files under ~/.helios/personas/."""
        personas_dir = helios_dir / "personas"
        if not personas_dir.exists():
            return {"status": "success", "personas": []}
        names = sorted(p.stem for p in personas_dir.glob("*.yaml"))
        return {"status": "success", "personas": names}

    # ------------------------------------------------------------------
    # Tool: get_behavioral_context
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Get the full behavioral context for a persona as system "
        "prompt text",
        tags={"behavioral", "context"},
        title="Get Behavioral Context",
        annotations=ToolAnnotations(
            title="Get Behavioral Context",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def get_behavioral_context(
        persona_name: str = Field(description="Persona name (e.g. 'developer')"),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> GetBehavioralContextResult:
        """Resolve the 4-level behavioral hierarchy and render as system prompt text."""
        try:
            from .hierarchy import IdentityHierarchy
            from .renderer import BehavioralRenderer

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)
            text = BehavioralRenderer().render(profile, persona_name)

            return {
                "status": "success",
                "persona": persona_name,
                "behavioral_context": text,
                "observation_count": profile.observation_count,
                "specialization_level": profile.specialization_level,
            }
        except Exception as e:
            logger.error(f"get_behavioral_context failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Tool: observe_interaction
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Observe a conversation and update behavioral fingerprint "
        "for a persona",
        tags={"behavioral", "observation"},
        title="Observe Interaction",
        annotations=ToolAnnotations(
            title="Observe Interaction",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
        ),
    )
    async def observe_interaction(
        persona_name: str = Field(description="Persona to observe for"),
        messages: list[dict[str, Any]] = Field(
            description="Conversation messages (role+content dicts)"
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ObserveInteractionResult:
        """Feed messages into the observation engine and check drift."""
        try:
            from .drift import DriftDetector
            from .hierarchy import IdentityHierarchy
            from .observer import BehavioralObserver

            observer = BehavioralObserver(helios_dir)
            observer.observe(persona_name, messages)
            count = observer.get_observation_count(persona_name)

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)
            observed_dists = observer.get_accumulated_distributions(persona_name)
            detector = DriftDetector()
            drift_result = detector.compute_drift(
                profile.distributions, observed_dists, count
            )

            return {
                "status": "success",
                "persona": persona_name,
                "observation_count": count,
                "current_drift": round(drift_result.total_drift, 4),
                "drift_threshold": DriftDetector.TOTAL_THRESHOLD,
                "negotiation_recommended": detector.exceeds_threshold(drift_result),
            }
        except Exception as e:
            logger.error(f"observe_interaction failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Tool: get_drift_report
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Get a natural language drift report — call when "
        "negotiation_recommended is true",
        tags={"behavioral", "drift"},
        title="Get Drift Report",
        annotations=ToolAnnotations(
            title="Get Drift Report",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def get_drift_report(
        persona_name: str = Field(description="Persona to report on"),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> GetDriftReportResult:
        """Generate a human-readable behavioral drift summary with a proposal."""
        try:
            from .drift import DriftDetector
            from .hierarchy import IdentityHierarchy
            from .negotiation import NegotiationEngine
            from .observer import BehavioralObserver

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)

            observer = BehavioralObserver(helios_dir)
            count = observer.get_observation_count(persona_name)
            if count == 0:
                return {
                    "status": "no_data",
                    "message": f"No observations for '{persona_name}'. "
                    "Use observe_interaction first.",
                }

            observed_dists = observer.get_accumulated_distributions(persona_name)
            detector = DriftDetector()
            drift_result = detector.compute_drift(
                profile.distributions, observed_dists, count
            )

            proposal = NegotiationEngine().generate_summary(
                persona_name, profile, observed_dists, drift_result
            )

            return {
                "status": "success",
                "persona": persona_name,
                "summary": proposal.summary,
                "per_dimension": proposal.per_dimension_summary,
                "total_drift": round(drift_result.total_drift, 4),
                "exceeds_threshold": drift_result.exceeds_total_threshold,
                "proposed_at": proposal.proposed_at,
            }
        except Exception as e:
            logger.error(f"get_drift_report failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Tool: negotiate_update
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Accept or reject a proposed behavioral update for a persona",
        tags={"behavioral", "negotiation"},
        title="Negotiate Behavioral Update",
        annotations=ToolAnnotations(
            title="Negotiate Behavioral Update",
            readOnlyHint=False,
            # On accept, this overwrites the persona's existing declared
            # distributions in place (profile.save() replaces the YAML file
            # and a git commit is made) — that is a destructive update to
            # the previously declared behavioral state, not an additive one.
            destructiveHint=True,
            idempotentHint=False,
        ),
    )
    async def negotiate_update(
        persona_name: str = Field(description="Persona to update"),
        decision: str = Field(description="'accept' or 'reject'"),
        reason: str = Field(default="", description="Optional reason for rejection"),
        accepted_dimensions: list[str] | None = Field(
            default=None,
            description="Specific dimensions to accept (None = accept all)",
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> NegotiateUpdateResult:
        """Apply or reject a behavioral evolution proposal. Accepted changes \
are git-committed."""
        try:
            from .drift import DriftDetector
            from .hierarchy import IdentityHierarchy
            from .negotiation import NegotiationEngine
            from .observer import BehavioralObserver

            engine = NegotiationEngine()

            if decision.lower() == "reject":
                rejected = engine.reject_update(
                    persona_name, reason or "user rejected", helios_dir
                )
                # Widened explicitly rather than cast: negotiation.py states its
                # exact return shape, while this tool's published schema is
                # total=False across every branch, so the keys are mapped by hand
                # to keep both sides type-checked.
                return NegotiateUpdateResult(
                    status=rejected["status"],
                    persona=rejected["persona"],
                    reason=rejected["reason"],
                )

            if decision.lower() == "accept":
                hierarchy = IdentityHierarchy(helios_dir)
                profile = hierarchy.resolve(persona_name)
                observer = BehavioralObserver(helios_dir)
                observed_dists = observer.get_accumulated_distributions(persona_name)
                count = observer.get_observation_count(persona_name)
                detector = DriftDetector()
                drift_result = detector.compute_drift(
                    profile.distributions, observed_dists, count
                )
                proposal = engine.generate_summary(
                    persona_name, profile, observed_dists, drift_result
                )
                applied = engine.apply_update(
                    persona_name, proposal, helios_dir, accepted_dimensions
                )
                return NegotiateUpdateResult(
                    status=applied["status"],
                    updated_dimensions=applied["updated_dimensions"],
                    commit_message=applied["commit_message"],
                )

            return {
                "status": "error",
                "message": f"Unknown decision '{decision}'. Use 'accept' or 'reject'.",
            }
        except Exception as e:
            logger.error(f"negotiate_update failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Tool: import_profile
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Import a personality file (CLAUDE.md, soul.md, etc.) into "
        "a Helios behavioral profile",
        tags={"behavioral", "import"},
        title="Import Profile",
        annotations=ToolAnnotations(
            title="Import Profile",
            readOnlyHint=False,
            # profile.save() writes unconditionally (os.replace) with no
            # existence check first, so importing with a persona_name (or a
            # derived agent_id) that already has a persona file silently
            # overwrites it.
            destructiveHint=True,
            idempotentHint=False,
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
        """Parse a personality file and create a new Helios persona \
with projected distributions."""
        try:
            from .importer import import_from_markdown

            path = Path(source_path).expanduser().resolve()
            profile = import_from_markdown(path)

            if persona_name:
                validate_persona_name(persona_name)
                profile.agent_id = persona_name

            # Save to personas directory
            personas_dir = helios_dir / "personas"
            personas_dir.mkdir(parents=True, exist_ok=True)
            out_path = personas_dir / f"{profile.agent_id}.yaml"
            profile.save(out_path)

            # Return summary
            summary: ImportProfileResult = {
                "status": "success",
                "persona": profile.agent_id,
                "source": str(path),
                "saved_to": str(out_path),
                "distributions": {},
            }
            for dim, dist in profile.distributions.items():
                summary["distributions"][dim] = {
                    "dominant": dist.most_likely(),
                    "entropy": round(dist.normalized_entropy(), 3),
                }

            return summary
        except Exception as e:
            logger.error(f"import_profile failed: {e}")
            return {"status": "error", "message": sanitize_error_message(e)}

    # ------------------------------------------------------------------
    # Tool: export_profile
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Export a behavioral profile in various formats "
        "(yaml, json, soulspec)",
        tags={"behavioral", "export"},
        title="Export Profile",
        annotations=ToolAnnotations(
            title="Export Profile",
            # Resolves the profile and serializes/returns it — no file or
            # state is written anywhere in this function.
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def export_profile(
        persona_name: str = Field(description="Persona to export"),
        format: str = Field(  # noqa: A002 - published MCP export-format parameter name
            default="yaml", description="Export format: yaml, json, or soulspec"
        ),
        dimensions: list[str] | None = Field(
            default=None,
            description="Specific dimensions to include (None = all)",
        ),
        ctx: Context | None = None,  # noqa: ARG001 - required by FastMCP tool signature
    ) -> ExportProfileResult:
        """Export a behavioral profile with optional dimension filtering."""
        try:
            from .exporter import export_dimensions, export_soulspec
            from .hierarchy import IdentityHierarchy

            validate_persona_name(persona_name)
            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)

            if format == "soulspec":
                return {
                    "status": "success",
                    "persona": persona_name,
                    "format": "soulspec",
                    "content": export_soulspec(profile),
                }

            exported = export_dimensions(profile, dimensions)
            # export_dimensions returns dict[str, Any]; mypy cannot verify a
            # ** expansion into a TypedDict, so build the result explicitly.
            # Keys/values are identical to the exported dict's own keys.
            return {
                "status": "success",
                "persona": persona_name,
                "format": format,
                "agent_id": exported["agent_id"],
                "level": exported["level"],
                "dimensions": exported["dimensions"],
            }
        except Exception as e:
            logger.error(f"export_profile failed: {e}")
            return {"status": "error", "message": sanitize_error_message(e)}

    logger.info(f"Helios MCP server created (config: {helios_dir})")
    return mcp
