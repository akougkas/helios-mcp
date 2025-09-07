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
@click.version_option(version="0.1.0", prog_name="helios-mcp")
def main(helios_dir: Path, verbose: bool) -> int:
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
        
        # Ensure the helios directory exists
        helios_dir.mkdir(parents=True, exist_ok=True)
        
        if verbose:
            logger.debug(f"Configuration directory created/verified: {helios_dir}")
        
        # Create and run the server
        logger.info(f"Starting Helios MCP server with configuration at {helios_dir}")
        
        # Run the server asynchronously
        asyncio.run(run_server(helios_dir, verbose))
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
        return 0
    except Exception as e:
        logger.error(f"Failed to start Helios MCP server: {e}")
        if verbose:
            logger.exception("Full error traceback:")
        return 1


async def run_server(helios_dir: Path, verbose: bool) -> None:
    """Run the Helios MCP server with specified configuration directory.
    
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
