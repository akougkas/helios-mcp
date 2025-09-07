"""CLI interface for Helios MCP server."""

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

from .server import create_server
from .lifecycle import managed_lifecycle
from .bootstrap import BootstrapManager
from .locking import ProcessLock
from .validation import ConfigValidator

# Configure logging to stderr only (stdio reserved for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Critical: no output to stdout for MCP protocol
)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--helios-dir",
    default=lambda: Path.home() / ".helios",
    type=click.Path(path_type=Path),
    help="Directory for Helios configurations (default: ~/.helios)"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose logging for debugging"
)
@click.option(
    "--health-check-interval",
    default=60.0,
    type=float,
    help="Interval in seconds for health checks (default: 60, 0 to disable)"
)
@click.option(
    "--shutdown-timeout",
    default=30.0,
    type=float,
    help="Timeout in seconds for graceful shutdown (default: 30)"
)
@click.version_option(version="0.1.0", prog_name="helios-mcp")
def main(
    helios_dir: Path, 
    verbose: bool, 
    health_check_interval: float, 
    shutdown_timeout: float
) -> int:
    """Start Helios MCP server.
    
    Helios is a configuration management system for AI behaviors with
    weighted inheritance. It allows AI agents to have persistent personalities
    that evolve over time.
    
    The server communicates via MCP (Model Context Protocol) over stdio.
    """
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
            bootstrap = BootstrapManager(helios_dir)
            
            if bootstrap.is_first_install():
                logger.info("First installation detected - bootstrapping Helios")
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
                logger.warning(f"Configuration validation issues found:")
                for error in validation_errors:
                    logger.warning(f"  - {error}")
                # Continue anyway - validator will have attempted recovery
            else:
                if verbose:
                    logger.debug("All configurations validated successfully")
            
            # Ensure the helios directory exists (redundant after bootstrap but safe)
            helios_dir.mkdir(parents=True, exist_ok=True)
            
            if verbose:
                logger.debug(f"Configuration directory verified: {helios_dir}")
            
            # Create and run the server with lifecycle management
            logger.info(f"Starting Helios MCP server with configuration at {helios_dir}")
            logger.info(f"Lifecycle: health checks every {health_check_interval}s, shutdown timeout {shutdown_timeout}s")
            
            # Run the server with lifecycle management
            try:
                loop = asyncio.get_running_loop()
                # Already in event loop (uvx/MCP context)
                loop.create_task(run_server_with_lifecycle(
                    helios_dir, verbose, health_check_interval, shutdown_timeout, process_lock
                ))
            except RuntimeError:
                # No event loop running, create one
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
            
            # Create the FastMCP server instance
            server = create_server(helios_dir)
            
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
        # Create the FastMCP server instance
        server = create_server(helios_dir)
        
        if verbose:
            logger.debug("FastMCP server instance created successfully")
        
        # Run the server (this handles stdio MCP protocol automatically)
        await server.run()
        
    except Exception as e:
        logger.error(f"Server runtime error: {e}")
        if verbose:
            logger.exception("Server runtime error traceback:")
        raise


# Critical: This makes uvx work correctly
if __name__ == "__main__":
    sys.exit(main())
