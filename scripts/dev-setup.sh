#!/bin/bash
# Development environment setup - UV 0.8.15+ ONLY (September 2025)

set -euo pipefail  # Exit on error, undefined vars, pipe failures

echo "🌞 Setting up Helios development environment with UV 0.8.15+..."
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Ensure UV is installed and check version
if ! command -v uv &> /dev/null; then
    echo "📦 Installing UV (latest version)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "  ✅ UV installed to ~/.local/bin"
fi

# Verify UV version
UV_VERSION=$(uv --version 2>/dev/null | cut -d' ' -f2 || echo "unknown")
echo "🔍 Found UV version: $UV_VERSION"

if [[ "$UV_VERSION" < "0.8.15" && "$UV_VERSION" != "unknown" ]]; then
    echo "⚠️  Warning: UV version $UV_VERSION is older than recommended 0.8.15"
    echo "  Consider upgrading: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# Install and configure Python 3.13
echo ""
echo "🐍 Installing Python 3.13 (recommended for September 2025)..."
uv python install 3.13
echo "  ✅ Python 3.13 installed"

echo "📌 Pinning project to Python 3.13..."
uv python pin 3.13
echo "  ✅ Project pinned to Python 3.13"

# Verify Python version
PYTHON_VERSION=$(uv run python --version 2>/dev/null | cut -d' ' -f2 || echo "unknown")
echo "  🔍 Using Python: $PYTHON_VERSION"

# Sync project dependencies
echo ""
echo "🔄 Syncing all project dependencies..."
uv sync --dev --all-extras
echo "  ✅ Dependencies synchronized"

# Show dependency tree
echo ""
echo "🌳 Dependency tree:"
uv tree --depth 2

# Install pre-commit hooks
echo ""
echo "🎯 Setting up pre-commit hooks..."
if uv run pre-commit install 2>/dev/null; then
    echo "  ✅ Pre-commit hooks installed"
else
    echo "  ⚠️  Pre-commit not found, skipping hook installation"
    echo "  Install with: uv add --dev pre-commit"
fi

# Run initial checks
echo ""
echo "🧪 Running initial code quality checks..."

# Format check
if command -v uv run ruff &> /dev/null; then
    echo "  🎨 Checking code formatting..."
    uv run ruff format --check . || true
fi

# Lint check
if command -v uv run ruff &> /dev/null; then
    echo "  🔍 Running linter..."
    uv run ruff check . || true
fi

# Type check
if command -v uv run mypy &> /dev/null; then
    echo "  📊 Running type checker..."
    uv run mypy src/helios --ignore-missing-imports || true
fi

# Display helpful information
echo ""
echo "========================================"
echo "✅ Development environment ready!"
echo "========================================"
echo ""
echo "🚀 Quick Start Commands:"
echo "  uv run helios serve       # Start the MCP server"
echo "  uv run pytest            # Run tests"
echo "  uv run ruff format .     # Format code"
echo "  uv run ruff check .      # Lint code"
echo "  uv run mypy src/helios   # Type check"
echo ""
echo "📊 Installed packages:"
uv pip list | head -10
echo "  ... (run 'uv pip list' for full list)"
echo ""
echo "📝 Project details:"
echo "  Python: $(uv run python --version)"
echo "  UV: $(uv --version)"
echo "  Location: $(pwd)"
echo ""
echo "🌐 Documentation: https://github.com/yourusername/helios-mcp"
echo "========================================"
