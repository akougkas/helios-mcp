# Developer Scripts

This directory contains optional developer tools for working with Helios MCP. These scripts are **not required** for using Helios - they're convenience tools for contributors and developers.

## Available Scripts

### `dev-setup.sh`
**Purpose**: Sets up a complete development environment for Helios MCP.

**What it does**:
- Installs/updates UV package manager (0.8.15+)
- Installs Python 3.13 via UV
- Syncs all project dependencies
- Sets up pre-commit hooks
- Runs initial code quality checks

**Usage**:
```bash
./scripts/dev-setup.sh
```

### `cleanup.sh`
**Purpose**: Prepares the repository for PyPI publication by removing temporary files.

**What it does**:
- Removes Python cache files (`__pycache__`, `*.pyc`)
- Cleans IDE files (`.DS_Store`, swap files)
- Optionally removes build artifacts (with `--full` flag)
- Verifies tests still pass after cleanup
- Shows repository status

**Usage**:
```bash
./scripts/cleanup.sh        # Keep dist/ for publishing
./scripts/cleanup.sh --full  # Remove all build artifacts
```

### `start_test_server.sh`
**Purpose**: Launches a local Helios MCP server for testing and development.

**What it does**:
- Checks dependencies are installed
- Runs quick test suite
- Starts the MCP server on stdio
- Shows Claude Desktop configuration example
- Supports verbose mode and custom Helios directories

**Usage**:
```bash
./scripts/start_test_server.sh           # Default ~/.helios
./scripts/start_test_server.sh --verbose # Enable debug logging
./scripts/start_test_server.sh --test    # Use temporary test directory
./scripts/start_test_server.sh --dir /custom/path  # Custom directory
```

## For Production Users

If you've installed Helios via PyPI, you don't need these scripts. Simply use:

```bash
# Install from PyPI
uvx helios-mcp

# Or with pip (though UV is recommended)
pip install helios-mcp
helios-mcp --help
```

## For Contributors

1. Clone the repository
2. Run `./scripts/dev-setup.sh` to set up your environment
3. Make your changes
4. Run `./scripts/cleanup.sh` before committing
5. Use `./scripts/start_test_server.sh` to test your changes locally

All scripts follow UV-exclusive development (no pip usage).