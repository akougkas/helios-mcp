#!/bin/bash
# Helios MCP Local Test Server Launcher

set -e

echo "🌞 Helios MCP Test Server Launcher"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Not in Helios MCP project directory"
    echo "Please run from: ~/projects/helios-mcp"
    exit 1
fi

# Parse arguments
VERBOSE=""
HELIOS_DIR="$HOME/.helios"
TEST_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE="--verbose"
            shift
            ;;
        --test|-t)
            TEST_MODE=true
            HELIOS_DIR="/tmp/helios_test_$(date +%s)"
            shift
            ;;
        --dir|-d)
            HELIOS_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./start_test_server.sh [options]"
            echo ""
            echo "Options:"
            echo "  -v, --verbose    Enable verbose logging"
            echo "  -t, --test       Use temporary test directory"
            echo "  -d, --dir PATH   Custom Helios directory (default: ~/.helios)"
            echo "  -h, --help       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}Configuration:${NC}"
echo "  Directory: $HELIOS_DIR"
echo "  Verbose: $([ -n "$VERBOSE" ] && echo "Yes" || echo "No")"
echo "  Test Mode: $([ "$TEST_MODE" = true ] && echo "Yes" || echo "No")"
echo ""

# Ensure dependencies are installed
echo -e "${YELLOW}Checking dependencies...${NC}"
uv sync --quiet

# Run tests first
echo -e "${YELLOW}Running quick test suite...${NC}"
if uv run pytest -q --tb=no 2>/dev/null; then
    echo -e "${GREEN}✅ All tests passing${NC}"
else
    echo -e "${YELLOW}⚠️  Some tests failed, but continuing...${NC}"
fi
echo ""

# Create test directory if in test mode
if [ "$TEST_MODE" = true ]; then
    echo -e "${YELLOW}Creating test directory: $HELIOS_DIR${NC}"
    mkdir -p "$HELIOS_DIR"
fi

# Start the server
echo -e "${GREEN}🚀 Starting Helios MCP Server...${NC}"
echo "=================================="
echo ""
echo "Server will listen for MCP connections on stdio"
echo "Press Ctrl+C to stop"
echo ""

# For Claude Desktop configuration, show the config
if [ "$TEST_MODE" = false ]; then
    echo -e "${BLUE}Claude Desktop Configuration:${NC}"
    echo '```json'
    cat << EOF
{
  "mcpServers": {
    "helios-local": {
      "command": "$(which uv)",
      "args": [
        "run",
        "python",
        "-m",
        "helios_mcp.cli"$([ -n "$VERBOSE" ] && echo ',
        "--verbose"')
      ],
      "cwd": "$(pwd)"
    }
  }
}
EOF
    echo '```'
    echo ""
fi

# Export environment variables
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
export HELIOS_DIR="$HELIOS_DIR"

# Start server with proper error handling
echo -e "${GREEN}Server starting...${NC}"
echo "-------------------"

# Trap Ctrl+C to exit gracefully
trap 'echo -e "\n${YELLOW}Shutting down server...${NC}"; exit 0' INT

# Run the server
if [ -n "$VERBOSE" ]; then
    uv run python -m helios_mcp.cli --helios-dir "$HELIOS_DIR" --verbose
else
    uv run python -m helios_mcp.cli --helios-dir "$HELIOS_DIR"
fi