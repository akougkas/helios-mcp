"""Helios MCP Server — behavioral science tools for AI agents."""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from fastmcp import FastMCP, Context
from pydantic import Field

from .security import validate_persona_name, sanitize_error_message, SecurityError, InvalidInputError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def create_server(helios_dir: Optional[Path] = None) -> FastMCP:
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
    )
    async def list_personas(ctx: Context = None) -> Dict[str, Any]:
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
        description="Get the full behavioral context for a persona as system prompt text",
        tags={"behavioral", "context"},
    )
    async def get_behavioral_context(
        persona_name: str = Field(description="Persona name (e.g. 'developer')"),
        ctx: Context = None,
    ) -> Dict[str, Any]:
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
        description="Observe a conversation and update behavioral fingerprint for a persona",
        tags={"behavioral", "observation"},
    )
    async def observe_interaction(
        persona_name: str = Field(description="Persona to observe for"),
        messages: list[Dict[str, Any]] = Field(description="Conversation messages (role+content dicts)"),
        ctx: Context = None,
    ) -> Dict[str, Any]:
        """Feed messages into the observation engine and check drift."""
        try:
            from .observer import BehavioralObserver
            from .drift import DriftDetector
            from .hierarchy import IdentityHierarchy

            observer = BehavioralObserver(helios_dir)
            observer.observe(persona_name, messages)
            count = observer.get_observation_count(persona_name)

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)
            observed_dists = observer.get_accumulated_distributions(persona_name)
            detector = DriftDetector()
            drift_result = detector.compute_drift(profile.distributions, observed_dists, count)

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
        description="Get a natural language drift report — call when negotiation_recommended is true",
        tags={"behavioral", "drift"},
    )
    async def get_drift_report(
        persona_name: str = Field(description="Persona to report on"),
        ctx: Context = None,
    ) -> Dict[str, Any]:
        """Generate a human-readable behavioral drift summary with a proposal."""
        try:
            from .observer import BehavioralObserver
            from .drift import DriftDetector
            from .negotiation import NegotiationEngine
            from .hierarchy import IdentityHierarchy

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)

            observer = BehavioralObserver(helios_dir)
            count = observer.get_observation_count(persona_name)
            if count == 0:
                return {
                    "status": "no_data",
                    "message": f"No observations for '{persona_name}'. Use observe_interaction first.",
                }

            observed_dists = observer.get_accumulated_distributions(persona_name)
            detector = DriftDetector()
            drift_result = detector.compute_drift(profile.distributions, observed_dists, count)

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
    )
    async def negotiate_update(
        persona_name: str = Field(description="Persona to update"),
        decision: str = Field(description="'accept' or 'reject'"),
        reason: str = Field(default="", description="Optional reason for rejection"),
        accepted_dimensions: Optional[list[str]] = Field(
            default=None,
            description="Specific dimensions to accept (None = accept all)",
        ),
        ctx: Context = None,
    ) -> Dict[str, Any]:
        """Apply or reject a behavioral evolution proposal. Accepted changes are git-committed."""
        try:
            from .observer import BehavioralObserver
            from .drift import DriftDetector
            from .negotiation import NegotiationEngine
            from .hierarchy import IdentityHierarchy

            engine = NegotiationEngine()

            if decision.lower() == "reject":
                return engine.reject_update(persona_name, reason or "user rejected", helios_dir)

            if decision.lower() == "accept":
                hierarchy = IdentityHierarchy(helios_dir)
                profile = hierarchy.resolve(persona_name)
                observer = BehavioralObserver(helios_dir)
                observed_dists = observer.get_accumulated_distributions(persona_name)
                count = observer.get_observation_count(persona_name)
                detector = DriftDetector()
                drift_result = detector.compute_drift(profile.distributions, observed_dists, count)
                proposal = engine.generate_summary(persona_name, profile, observed_dists, drift_result)
                return engine.apply_update(persona_name, proposal, helios_dir, accepted_dimensions)

            return {"status": "error", "message": f"Unknown decision '{decision}'. Use 'accept' or 'reject'."}
        except Exception as e:
            logger.error(f"negotiate_update failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Tool: import_profile
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Import a personality file (CLAUDE.md, soul.md, etc.) into a Helios behavioral profile",
        tags={"behavioral", "import"},
    )
    async def import_profile(
        source_path: str = Field(description="Path to the personality file to import"),
        persona_name: str = Field(default="", description="Name for the new persona (default: derived from filename)"),
        ctx: Context = None,
    ) -> Dict[str, Any]:
        """Parse a personality file and create a new Helios persona with projected distributions."""
        try:
            from .importer import import_from_markdown
            from .profile import BehavioralProfile

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
            summary: Dict[str, Any] = {
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
            return {"status": "error", "message": sanitize_error_message(str(e))}

    # ------------------------------------------------------------------
    # Tool: export_profile
    # ------------------------------------------------------------------

    @mcp.tool(
        description="Export a behavioral profile in various formats (yaml, json, soulspec)",
        tags={"behavioral", "export"},
    )
    async def export_profile(
        persona_name: str = Field(description="Persona to export"),
        format: str = Field(default="yaml", description="Export format: yaml, json, or soulspec"),
        dimensions: Optional[list[str]] = Field(default=None, description="Specific dimensions to include (None = all)"),
        ctx: Context = None,
    ) -> Dict[str, Any]:
        """Export a behavioral profile with optional dimension filtering."""
        try:
            from .hierarchy import IdentityHierarchy
            from .exporter import export_dimensions, export_soulspec

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
            return {
                "status": "success",
                "persona": persona_name,
                "format": format,
                **exported,
            }
        except Exception as e:
            logger.error(f"export_profile failed: {e}")
            return {"status": "error", "message": sanitize_error_message(str(e))}

    logger.info(f"Helios MCP server created (config: {helios_dir})")
    return mcp
