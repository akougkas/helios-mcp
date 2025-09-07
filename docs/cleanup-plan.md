# Helios MCP Repository Cleanup Plan

## Executive Summary

This plan prepares the Helios MCP repository for PyPI publication by removing temporary files, reorganizing test structure, and ensuring a clean, professional project layout.

## Current Issues Identified

### 1. Test Files in Root Directory
- `test_import.py` - Temporary import validation script
- `test_tools.py` - Early tool testing script  
- `test_integration.py` - Integration test (duplicate of tests/test_server.py)
- `test_quick.py` - Quick validation script
- `test_final.py` - Final integration test

**Action**: Remove all root-level test files (tests are properly located in `tests/` directory)

### 2. Python Cache Files
Multiple `__pycache__` directories and `.pyc` files exist:
- `src/helios_mcp/__pycache__/`
- `tests/__pycache__/`

**Action**: Clean all Python cache files

### 3. Build Artifacts
- `dist/` directory contains wheels and tarballs

**Action**: Already in `.gitignore`, safe to keep for publishing

### 4. Version Control Issues
- `uv.lock` is tracked but listed in `.gitignore` (line 88)

**Action**: Keep `uv.lock` tracked for reproducible builds (update .gitignore)

## Cleanup Actions

### Phase 1: Remove Temporary Test Files
```bash
# Remove root-level test files
rm test_import.py
rm test_tools.py
rm test_integration.py
rm test_quick.py
rm test_final.py
```

### Phase 2: Clean Python Cache
```bash
# Remove all __pycache__ directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
```

### Phase 3: Update .gitignore
Remove line 88 (`uv.lock`) from `.gitignore` since lock files should be tracked for reproducible builds.

Add:
```
# Test artifacts
test_*.py
*.test.py

# Temporary development files
*.tmp
*.debug
scratch/
```

## Final Clean Structure

```
helios-mcp/
├── .gitignore              # Updated with proper patterns
├── .python-version         # Python 3.13 requirement
├── LICENSE                 # MIT License
├── README.md              # User documentation
├── pyproject.toml         # Package configuration
├── uv.lock                # Dependency lock (keep tracked)
│
├── src/
│   └── helios_mcp/
│       ├── __init__.py    # Package initialization
│       ├── cli.py         # CLI entry point
│       ├── config.py      # Configuration management
│       ├── git_store.py   # Git persistence
│       ├── inheritance.py # Core inheritance model
│       └── server.py      # MCP server implementation
│
├── tests/
│   ├── __init__.py        # Test package marker
│   ├── conftest.py        # Pytest configuration
│   ├── test_cli.py        # CLI tests
│   └── test_server.py     # Server integration tests
│
├── samples/               # Example configurations
│   ├── base/
│   │   └── identity.yaml
│   └── personas/
│       ├── coder.yaml
│       ├── developer.yaml
│       └── researcher.yaml
│
├── docs/                  # Technical documentation
│   ├── architecture.md
│   ├── architecture-review.md
│   ├── cleanup-plan.md    # This document
│   ├── fastmcp-testing.md
│   ├── git-persistence.md
│   ├── mcp-claude-config.md
│   ├── pypi-publishing.md
│   ├── uv-project-setup.md
│   └── uvx-cli-patterns.md
│
├── planning/              # Project planning
│   ├── PLAN.md
│   └── PRD.md
│
├── scripts/               # Development scripts
│   └── dev-setup.sh
│
├── CLAUDE.md             # AI assistant configuration
└── DEVLOG.md             # Development log

# Ignored (not in repo):
├── dist/                 # Build artifacts (for PyPI upload)
├── .uv/                  # UV cache
└── **/__pycache__/       # Python cache
```

## Validation Checklist

- [ ] All test files consolidated in `tests/` directory
- [ ] No Python cache files (`__pycache__`, `*.pyc`)
- [ ] Clean root directory (no test_*.py files)
- [ ] `.gitignore` updated for production
- [ ] `uv.lock` properly tracked
- [ ] Documentation organized in `docs/`
- [ ] Samples in clear structure
- [ ] Ready for `uv publish`

## Production .gitignore Updates

Key patterns for production:
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Distribution
build/
dist/
*.egg-info/
*.egg

# UV
.uv/
# Note: uv.lock should be tracked

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Development
*.tmp
*.debug
test_*.py
scratch/

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# Environment
.env
.env.local
venv/
.venv/

# Helios runtime (user data)
~/.helios/
```

## Execution Commands

Run these commands in order:

```bash
# 1. Clean test files
rm test_import.py test_tools.py test_integration.py test_quick.py test_final.py

# 2. Clean Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete

# 3. Verify tests still work
uv run pytest

# 4. Commit cleanup
git add -A
git commit -m "Clean repository structure for PyPI publication"

# 5. Ready for publishing
uv build
uv publish
```

## Post-Cleanup Verification

After cleanup, verify:
1. `uv run pytest` - All tests pass
2. `uv run helios-mcp --version` - CLI works
3. `uv build` - Package builds cleanly
4. Repository is professional and publication-ready

## Notes

- The `dist/` directory is kept for PyPI uploads but ignored by git
- `uv.lock` should be tracked for reproducible builds
- All development test files moved to proper `tests/` directory
- Documentation well-organized in `docs/`
- Clean, minimal root directory structure