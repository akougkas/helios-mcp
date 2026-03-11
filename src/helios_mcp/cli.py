"""CLI interface for Helios MCP server."""

import os
import sys
import asyncio
import logging
from pathlib import Path

try:
    import click
except ImportError:
    print("Click is required: uv add click>=8.1.0", file=sys.stderr)
    sys.exit(1)

from . import __version__
from .server import create_server
from .bootstrap import BootstrapManager
from .hierarchy import IdentityHierarchy
from .hook_events import parse_hook_stdin
from .observer import BehavioralObserver
from .drift import DriftDetector
from .taxonomy import list_dimensions

log_level_str = os.getenv("HELIOS_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv("HELIOS_DIR", Path.home() / ".helios")),
    type=click.Path(path_type=Path),
    help="Helios config directory (default: ~/.helios, env: HELIOS_DIR)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.version_option(version=__version__, prog_name="helios-mcp")
@click.pass_context
def main(ctx: click.Context, helios_dir: Path, verbose: bool) -> int:
    """Helios MCP server — behavioral science for AI agents.

    Run without a subcommand to start the MCP server over stdio.
    Use subcommands (status, negotiate) for behavioral inspection.
    """
    ctx.ensure_object(dict)
    ctx.obj["helios_dir"] = helios_dir
    ctx.obj["verbose"] = verbose

    if ctx.invoked_subcommand is not None:
        return 0

    # Default: start the MCP server
    try:
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        bootstrap = BootstrapManager(helios_dir)
        if bootstrap.is_first_install():
            logger.info("First run — bootstrapping Helios")
            bootstrap.bootstrap_installation()
        else:
            bootstrap.update_last_boot()

        asyncio.run(_run_server(helios_dir, verbose))
        return 0

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
        return 0
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        if verbose:
            logger.exception("Traceback:")
        return 1


@main.command("status")
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv("HELIOS_DIR", Path.home() / ".helios")),
    type=click.Path(path_type=Path),
)
def status_command(helios_dir: Path) -> None:
    """Print current behavioral profile state for all personas."""
    click.echo("Helios v2 Status")
    click.echo("================")
    click.echo(f"Helios directory: {helios_dir}")

    base_dir = helios_dir / "base"
    personas_dir = helios_dir / "personas"

    if not base_dir.exists():
        click.echo("\nNo profiles found — run 'helios-mcp' to bootstrap.")
        return

    persona_names: list[str] = []
    if personas_dir.exists():
        persona_names = [
            p.stem for p in sorted(personas_dir.glob("*.yaml"))
            if not p.stem.endswith("_user")
        ]

    if persona_names:
        click.echo(f"Personas: {', '.join(persona_names)} ({len(persona_names)} found)")
    else:
        click.echo("Personas: none found")

    hierarchy = IdentityHierarchy(helios_dir)

    for persona_name in persona_names:
        try:
            profile = hierarchy.resolve(persona_name)
            click.echo(f"\n{persona_name} profile:")
            for dim, dist in profile.distributions.items():
                ne = dist.normalized_entropy()
                dominant = dist.most_likely()
                prob = dist.probs[dist.states.index(dominant)]
                label = "low" if ne < 0.3 else ("moderate" if ne <= 0.6 else "high")
                click.echo(f"  {dim:<28} {dominant} ({prob:.2f}) — entropy: {label}")
        except Exception as exc:
            click.echo(f"\n{persona_name} profile: error ({exc})")


@main.command("negotiate")
@click.argument("persona")
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv("HELIOS_DIR", Path.home() / ".helios")),
    type=click.Path(path_type=Path),
)
@click.option("--threshold", default=0.30, type=float, help="Drift threshold (default: 0.30)")
def negotiate_command(persona: str, helios_dir: Path, threshold: float) -> None:
    """Show drift report for PERSONA and prompt for action."""
    observer = BehavioralObserver()
    detector = DriftDetector()
    hierarchy = IdentityHierarchy(helios_dir)

    obs_count = observer.get_observation_count(persona)
    if obs_count == 0:
        click.echo(f"No observations for '{persona}'.")
        return

    try:
        profile = hierarchy.resolve(persona)
    except Exception as exc:
        click.echo(f"Failed to load profile for '{persona}': {exc}")
        return

    observed = observer.get_accumulated_distributions(persona)
    result = detector.compute_drift(profile.distributions, observed, obs_count)

    click.echo(f"Drift Report for '{persona}'")
    click.echo("=" * (len(persona) + 20))

    flag = " !! " if result.exceeds_total_threshold else " ok"
    click.echo(f"Total drift: {result.total_drift:.2f} (threshold: {threshold}){flag}")
    click.echo(f"Observations: {obs_count}")
    click.echo("\nPer-dimension drift:")

    for dim in list_dimensions():
        kl = result.per_dimension.get(dim, 0.0)
        dim_flag = "!!" if kl >= detector.PER_DIM_THRESHOLD else "ok"
        declared_dist = profile.distributions.get(dim)
        observed_dist = observed.get(dim)
        declared_state = declared_dist.most_likely() if declared_dist else "unknown"
        observed_state = observed_dist.most_likely() if observed_dist else "unknown"
        click.echo(f"  {dim:<28} {kl:.2f} {dim_flag}  (declared: {declared_state}, observed: {observed_state})")

    click.echo("")
    action = click.prompt("[A]ccept all  [R]eject  [Q]uit", default="Q", show_default=False)
    action = action.strip().upper()

    if action == "A":
        click.echo("Changes accepted.")
    elif action == "R":
        click.echo("Changes rejected.")
    else:
        click.echo("No action taken.")


# ---------------------------------------------------------------------------
# Hook event handlers (Task 1.4)
# ---------------------------------------------------------------------------

_VALID_HOOK_EVENTS = (
    "pre-tool", "post-tool",
    "subagent-start", "subagent-stop",
    "session-start", "session-end",
    "notification", "prompt-submit", "stop",
)


@main.command("hook")
@click.argument("event_type", type=click.Choice(_VALID_HOOK_EVENTS))
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv("HELIOS_DIR", Path.home() / ".helios")),
    type=click.Path(path_type=Path),
)
@click.option("--persona", default="default", help="Persona to record observation for")
def hook_command(event_type: str, helios_dir: Path, persona: str) -> None:
    """Process a Claude Code hook event from stdin.

    Reads JSON from stdin, parses it into a typed event, and persists
    the observation to the Helios store. Designed to be fast (< 100ms)
    and non-blocking. Always exits 0 to avoid blocking Claude Code.
    """
    import json as _json

    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            raw_json: dict = {}
        else:
            raw_json = _json.loads(raw_input)
            if not isinstance(raw_json, dict):
                raw_json = {}

        event = parse_hook_stdin(raw_json, event_type)

        # Persist the event to the observation store
        obs_dir = helios_dir / "observations" / "hooks"
        obs_dir.mkdir(parents=True, exist_ok=True)

        obs_file = obs_dir / f"{persona}.jsonl"
        record = {
            "event_type": event_type,
            "timestamp": event.timestamp,
            "data": raw_json,
        }
        with obs_file.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(record) + "\n")

        logger.debug("Processed %s event for persona %s", event_type, persona)

    except Exception as exc:
        # Log but never fail. Hook handlers must exit 0.
        logger.debug("Hook handler error for %s: %s", event_type, exc)

    sys.exit(0)


async def _run_server(helios_dir: Path, verbose: bool) -> None:
    """Start the MCP server over stdio."""
    server = await create_server(helios_dir)
    if verbose:
        logger.debug("FastMCP server created")
    await server.run()


if __name__ == "__main__":
    sys.exit(main())
