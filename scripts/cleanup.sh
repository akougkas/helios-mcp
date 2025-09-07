#!/bin/bash
# Cleanup script for Helios MCP repository
# Prepares the repository for PyPI publication

set -e  # Exit on error

echo "🧹 Helios MCP Repository Cleanup"
echo "================================"

# Function to print colored output
print_step() {
    echo -e "\n✨ $1"
}

print_success() {
    echo -e "✅ $1"
}

print_error() {
    echo -e "❌ $1"
}

# Get the repository root (parent of scripts directory)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

print_step "Starting cleanup in: $REPO_ROOT"

# Step 1: Remove root-level test files
print_step "Removing temporary test files from root..."
for file in test_import.py test_tools.py test_integration.py test_quick.py test_final.py; do
    if [ -f "$file" ]; then
        rm "$file"
        print_success "Removed $file"
    fi
done

# Step 2: Clean Python cache files
print_step "Cleaning Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type f -name "*.pyd" -delete 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
print_success "Python cache cleaned"

# Step 3: Clean build artifacts (optional, keeping dist for publishing)
if [ "$1" == "--full" ]; then
    print_step "Cleaning build artifacts (--full mode)..."
    rm -rf build/ dist/ *.egg-info
    print_success "Build artifacts cleaned"
else
    print_step "Keeping dist/ directory for PyPI publishing (use --full to remove)"
fi

# Step 4: Clean IDE and editor files
print_step "Cleaning IDE and editor files..."
find . -name ".DS_Store" -delete 2>/dev/null || true
find . -name "*.swp" -delete 2>/dev/null || true
find . -name "*.swo" -delete 2>/dev/null || true
find . -name "*~" -delete 2>/dev/null || true
print_success "IDE files cleaned"

# Step 5: Verify tests still work
print_step "Verifying tests..."
if uv run pytest -q; then
    print_success "All tests pass"
else
    print_error "Tests failed! Please check before proceeding"
    exit 1
fi

# Step 6: Show repository status
print_step "Repository status:"
echo ""
echo "📁 Directory structure:"
tree -L 2 -I "__pycache__|*.pyc|.git|.uv" 2>/dev/null || {
    # Fallback if tree is not installed
    echo "Main directories:"
    ls -la | grep "^d" | awk '{print "  " $NF}' | grep -v "^\.$\|^\.\.$"
}

echo ""
echo "📊 File count by type:"
echo "  Python files: $(find src tests -name "*.py" | wc -l)"
echo "  Test files: $(find tests -name "test_*.py" | wc -l)"
echo "  Documentation: $(find docs -name "*.md" | wc -l)"
echo "  YAML configs: $(find samples -name "*.yaml" | wc -l)"

echo ""
print_success "Cleanup complete! Repository is ready for:"
echo "  1. git add -A && git commit -m 'Clean repository for PyPI'"
echo "  2. uv build"
echo "  3. uv publish"

# Optional: Show git status
if command -v git &> /dev/null; then
    echo ""
    print_step "Git status:"
    git status --short
fi