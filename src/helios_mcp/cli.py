"""CLI interface for Helios MCP server."""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional

try:
    import click
except ImportError:
    print("Click is required for CLI functionality. Install with: uv add click>=8.1.0", file=sys.stderr)
    sys.exit(1)

from . import __version__
from .server import create_server
from .lifecycle import managed_lifecycle
from .bootstrap import BootstrapManager
from .locking import ProcessLock
from .validation import ConfigValidator
from .hierarchy import IdentityHierarchy
from .observer import BehavioralObserver
from .drift import DriftDetector
from .taxonomy import list_dimensions

# Configure logging to stderr only (stdio reserved for MCP protocol)
# Support HELIOS_LOG_LEVEL environment variable
log_level_str = os.getenv('HELIOS_LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Critical: no output to stdout for MCP protocol
)
logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv('HELIOS_DIR', Path.home() / ".helios")),
    type=click.Path(path_type=Path),
    help="Directory for Helios configurations (default: ~/.helios, env: HELIOS_DIR)"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose logging for debugging"
)
@click.option(
    "--health-check-interval",
    default=lambda: float(os.getenv('HELIOS_HEALTH_CHECK_INTERVAL', '60.0')),
    type=float,
    help="Interval in seconds for health checks (default: 60, 0 to disable, env: HELIOS_HEALTH_CHECK_INTERVAL)"
)
@click.option(
    "--shutdown-timeout",
    default=30.0,
    type=float,
    help="Timeout in seconds for graceful shutdown (default: 30)"
)
@click.option(
    "--disable-git",
    is_flag=True,
    default=lambda: os.getenv('HELIOS_GIT_ENABLED', '1').lower() in ('0', 'false', 'no'),
    help="Disable git operations (for containerized environments, env: HELIOS_GIT_ENABLED=0)"
)
@click.version_option(version=__version__, prog_name="helios-mcp")
@click.pass_context
def main(
    ctx: click.Context,
    helios_dir: Path,
    verbose: bool,
    health_check_interval: float,
    shutdown_timeout: float,
    disable_git: bool,
) -> int:
    """Helios MCP server and behavioral management CLI.

    Run without a subcommand to start the MCP server over stdio.
    Use subcommands (status, negotiate) for behavioral inspection.

    Helios is a configuration management system for AI behaviors with
    weighted inheritance. It allows AI agents to have persistent personalities
    that evolve over time.
    """
    # Store shared options in Click context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["helios_dir"] = helios_dir
    ctx.obj["verbose"] = verbose

    # If a subcommand was invoked, let it handle everything
    if ctx.invoked_subcommand is not None:
        return 0

    # Default behaviour: start the MCP server
    try:
        # Configure logging level based on verbose flag
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.debug(f"Starting Helios MCP server with config directory: {helios_dir}")

        # Acquire process lock to prevent multiple instances
        process_lock = ProcessLock(helios_dir)
        if not process_lock.acquire():
            logger.error("Another Helios instance is already running")
            return 1

        try:
            # Bootstrap installation if needed
            bootstrap = BootstrapManager(helios_dir, git_enabled=not disable_git)

            if bootstrap.is_first_install():
                logger.info("First installation detected - bootstrapping Helios")
                if disable_git:
                    logger.info("Git operations disabled via configuration")
                bootstrap.bootstrap_installation()
                logger.info("Bootstrap complete - Helios is ready to use")
            else:
                # Update last boot timestamp
                bootstrap.update_last_boot()
                if verbose:
                    install_info = bootstrap.get_installation_info()
                    logger.debug(f"Helios installation info: {install_info}")

            # Validate all configurations after bootstrap
            validator = ConfigValidator(helios_dir)
            validation_errors = validator.validate_all_configs(helios_dir)

            if validation_errors:
                logger.warning("Configuration validation issues found:")
                for error in validation_errors:
                    logger.warning(f"  - {error}")
                # Continue anyway - validator will have attempted recovery
            else:
                if verbose:
                    logger.debug("All configurations validated successfully")

            # Perform startup health check
            startup_health = _perform_startup_health_check(helios_dir, verbose)
            if not startup_health['healthy']:
                logger.warning("Startup health check issues detected:")
                for issue in startup_health['issues']:
                    logger.warning(f"  - {issue}")
                # Continue with warnings but don't fail startup
            elif verbose:
                logger.debug("Startup health check passed")

            # Ensure the helios directory exists (redundant after bootstrap but safe)
            helios_dir.mkdir(parents=True, exist_ok=True)

            if verbose:
                logger.debug(f"Configuration directory verified: {helios_dir}")

            # Create and run the server with lifecycle management
            logger.info(f"Starting Helios MCP server with configuration at {helios_dir}")
            logger.info(
                f"Lifecycle: health checks every {health_check_interval}s, "
                f"shutdown timeout {shutdown_timeout}s"
            )

            # Run the server with lifecycle management
            asyncio.run(run_server_with_lifecycle(
                helios_dir, verbose, health_check_interval, shutdown_timeout, process_lock
            ))

            return 0

        finally:
            # Always release the process lock
            process_lock.release()

    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
        return 0
    except Exception as e:
        logger.error(f"Failed to start Helios MCP server: {e}")
        if verbose:
            logger.exception("Full error traceback:")
        return 1


@main.command("status")
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv('HELIOS_DIR', Path.home() / ".helios")),
    type=click.Path(path_type=Path),
    help="Directory for Helios configurations (default: ~/.helios, env: HELIOS_DIR)"
)
def status_command(helios_dir: Path) -> None:
    """Print current behavioral profile state for all personas."""
    click.echo("Helios v2 Status")
    click.echo("================")
    click.echo(f"Helios directory: {helios_dir}")

    personas_dir = helios_dir / "personas"
    base_dir = helios_dir / "base"

    if not base_dir.exists():
        click.echo("\nNo profiles found — run 'helios-mcp init' to get started.")
        return

    # Collect available persona names from YAML files in personas/
    persona_names: list[str] = []
    if personas_dir.exists():
        persona_names = [
            p.stem for p in sorted(personas_dir.glob("*.yaml"))
            if not p.stem.endswith("_user")
        ]

    if persona_names:
        names_str = ", ".join(persona_names)
        click.echo(f"Personas: {names_str} ({len(persona_names)} found)")
    else:
        click.echo("Personas: none found")

    # Show profile details for each persona
    hierarchy = IdentityHierarchy(helios_dir)

    def _entropy_label(ne: float) -> str:
        if ne < 0.3:
            return "low"
        if ne <= 0.6:
            return "moderate"
        return "high"

    for persona_name in persona_names:
        try:
            profile = hierarchy.resolve(persona_name)
            click.echo(f"\n{persona_name} profile:")
            for dim, dist in profile.distributions.items():
                ne = dist.normalized_entropy()
                dominant = dist.most_likely()
                prob = dist.probs[dist.states.index(dominant)]
                entropy_label = _entropy_label(ne)
                click.echo(
                    f"  {dim:<28} {dominant} ({prob:.2f}) — entropy: {entropy_label}"
                )
        except Exception as exc:
            click.echo(f"\n{persona_name} profile: error loading ({exc})")


@main.command("negotiate")
@click.argument("persona")
@click.option(
    "--helios-dir",
    default=lambda: Path(os.getenv('HELIOS_DIR', Path.home() / ".helios")),
    type=click.Path(path_type=Path),
    help="Directory for Helios configurations (default: ~/.helios, env: HELIOS_DIR)"
)
@click.option(
    "--threshold",
    default=0.30,
    type=float,
    help="Drift threshold for flagging dimensions (default: 0.30)"
)
def negotiate_command(persona: str, helios_dir: Path, threshold: float) -> None:
    """Show drift report for PERSONA and prompt for action."""
    observer = BehavioralObserver()
    detector = DriftDetector()
    hierarchy = IdentityHierarchy(helios_dir)

    obs_count = observer.get_observation_count(persona)

    if obs_count == 0:
        click.echo(f"No observations recorded yet for '{persona}'.")
        return

    try:
        profile = hierarchy.resolve(persona)
    except Exception as exc:
        click.echo(f"Failed to load profile for '{persona}': {exc}")
        return

    observed = observer.get_accumulated_distributions(persona)
    result = detector.compute_drift(profile.distributions, observed, obs_count)

    # Header
    click.echo(f"Drift Report for '{persona}'")
    click.echo("=" * (len(persona) + 20))

    total_flag = " ⚠️ " if result.exceeds_total_threshold else " ✓"
    click.echo(
        f"Total drift: {result.total_drift:.2f} (threshold: {threshold}){total_flag}"
    )
    click.echo(f"Observations: {obs_count}")
    click.echo("\nPer-dimension drift:")

    for dim in list_dimensions():
        kl = result.per_dimension.get(dim, 0.0)
        flag = "⚠️ " if kl >= detector.PER_DIM_THRESHOLD else "✓"
        declared_dist = profile.distributions.get(dim)
        observed_dist = observed.get(dim)

        declared_state = declared_dist.most_likely() if declared_dist else "unknown"
        observed_state = observed_dist.most_likely() if observed_dist else "unknown"

        click.echo(
            f"  {dim:<28} {kl:.2f} {flag}  "
            f"(declared: {declared_state}, observed: {observed_state})"
        )

    click.echo("")
    action = click.prompt(
        "[A]ccept all changes  [R]eject  [Q]uit",
        default="Q",
        show_default=False,
    )
    action = action.strip().upper()

    if action == "A":
        click.echo("Changes accepted. Run 'evolve_behavior' to promote to persona config.")
    elif action == "R":
        click.echo("Changes rejected. Behavioral profile unchanged.")
    else:
        click.echo("No action taken.")


async def run_server_with_lifecycle(
    helios_dir: Path, 
    verbose: bool, 
    health_check_interval: float, 
    shutdown_timeout: float,
    process_lock: ProcessLock
) -> None:
    """Run the Helios MCP server with lifecycle management.
    
    Args:
        helios_dir: Path to the Helios configuration directory
        verbose: Whether to enable verbose logging
        health_check_interval: Seconds between health checks (0 to disable)
        shutdown_timeout: Max seconds to wait for graceful shutdown
    """
    logger.info(f"Starting Helios MCP server with lifecycle management")
    logger.info(f"Health checks: {health_check_interval}s interval, Shutdown timeout: {shutdown_timeout}s")
    
    try:
        async with managed_lifecycle(
            helios_dir=helios_dir,
            health_check_interval=health_check_interval,
            shutdown_timeout=shutdown_timeout,
            process_lock=process_lock
        ) as lifecycle_manager:
            
            logger.info("Lifecycle manager started successfully")
            
            # Create the FastMCP server instance with performance optimizations
            server = await create_server(helios_dir, preload_cache=True)
            
            if verbose:
                logger.debug("FastMCP server instance created successfully")
            
            # Log initial health status
            health_status = await lifecycle_manager.check_health()
            if health_status["healthy"]:
                logger.info("Initial health check passed - server ready")
            else:
                logger.warning(f"Health check issues: {health_status['issues']}")
            
            # Run the server (this handles stdio MCP protocol automatically)
            # The lifecycle manager will handle graceful shutdown via signal handlers
            await server.run()
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested via keyboard interrupt")
    except Exception as e:
        logger.error(f"Server runtime error: {e}")
        if verbose:
            logger.exception("Server runtime error traceback:")
        raise
    finally:
        logger.info("Server shutdown complete")


async def run_server(helios_dir: Path, verbose: bool) -> None:
    """Legacy server runner without lifecycle management.
    
    Maintained for compatibility. Use run_server_with_lifecycle for production.
    
    Args:
        helios_dir: Path to the Helios configuration directory
        verbose: Whether to enable verbose logging
    """
    try:
        # Create the FastMCP server instance with performance optimizations
        server = await create_server(helios_dir, preload_cache=True)
        
        if verbose:
            logger.debug("FastMCP server instance created successfully")
        
        # Run the server (this handles stdio MCP protocol automatically)
        await server.run()
        
    except Exception as e:
        logger.error(f"Server runtime error: {e}")
        if verbose:
            logger.exception("Server runtime error traceback:")
        raise


def _perform_startup_health_check(helios_dir: Path, verbose: bool) -> dict:
    """Perform comprehensive startup health check.
    
    Args:
        helios_dir: Path to Helios configuration directory
        verbose: Whether to enable verbose logging
        
    Returns:
        Dictionary with health status and any issues found
    """
    issues = []
    
    try:
        # Check directory structure
        required_dirs = ['base', 'personas', 'learned', 'temporary']
        for dir_name in required_dirs:
            dir_path = helios_dir / dir_name
            if not dir_path.exists():
                issues.append(f"Missing required directory: {dir_path}")
            elif not dir_path.is_dir():
                issues.append(f"Path exists but is not a directory: {dir_path}")
        
        # Check base configuration exists and is valid
        base_config = helios_dir / "base" / "identity.yaml"
        if not base_config.exists():
            issues.append("Base identity configuration missing")
        else:
            from .atomic_ops import validate_yaml_file
            if not validate_yaml_file(base_config):
                issues.append("Base identity configuration is invalid YAML")
        
        # Check git repository status (if git operations enabled)
        git_enabled = not os.getenv('HELIOS_GIT_ENABLED', '1').lower() in ('0', 'false', 'no')
        if git_enabled:
            git_dir = helios_dir / ".git"
            if not git_dir.exists():
                issues.append("Git repository not initialized (required for learning system)")
        
        # Check write permissions
        try:
            test_file = helios_dir / ".health_check_test"
            test_file.write_text("test", encoding='utf-8')
            test_file.unlink()
        except (OSError, PermissionError) as e:
            issues.append(f"No write permission to configuration directory: {e}")
        
        # Check available disk space (warn if < 100MB)
        try:
            import shutil
            total, used, free = shutil.disk_usage(helios_dir)
            free_mb = free / (1024 * 1024)
            if free_mb < 100:
                issues.append(f"Low disk space: {free_mb:.1f}MB available (recommended: >100MB)")
        except OSError as e:
            issues.append(f"Could not check disk space: {e}")
        
        # Validate schema versions in existing configs
        config_files = []
        for pattern in ['base/*.yaml', 'personas/*.yaml']:
            config_files.extend(helios_dir.glob(pattern))
        
        for config_file in config_files:
            try:
                import yaml
                with config_file.open('r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                
                if not isinstance(config_data, dict):
                    issues.append(f"Config file has invalid format: {config_file}")
                    continue
                    
                if 'schema_version' not in config_data:
                    issues.append(f"Config file missing schema_version: {config_file}")
                    
            except Exception as e:
                issues.append(f"Could not validate config file {config_file}: {e}")
        
        if verbose and not issues:
            logger.debug("All startup health checks passed")
            
    except Exception as e:
        issues.append(f"Health check system error: {e}")
    
    return {
        'healthy': len(issues) == 0,
        'issues': issues
    }


# Critical: This makes uvx work correctly
if __name__ == "__main__":
    sys.exit(main())
