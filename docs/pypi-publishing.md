# UV PyPI Publishing Guide (September 2025)
**Updated**: 2025-09-07
**Version**: UV 0.8.15+
**Source**: Official UV docs, PyPI guidelines, PEP 621

## Quick Reference - Ship TODAY

### Essential Commands
```bash
# 1. Build package (creates dist/ directory)
uv build

# 2. Test locally before publishing
uv run --with ./dist/helios_mcp-0.1.0-py3-none-any.whl --no-project -- python -c "import helios_mcp"

# 3. Publish to PyPI (with token)
uv publish --token $PYPI_TOKEN

# Alternative: Test on TestPyPI first
uv publish --publish-url https://test.pypi.org/legacy/ --token $TESTPYPI_TOKEN
```

## Required pyproject.toml for PyPI

### Minimal Configuration
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "helios-mcp"
version = "0.1.0"
description = "AI personality management via weighted configuration inheritance"
readme = "README.md"
requires-python = ">=3.13"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
dependencies = [
    "fastmcp>=2.2.6",
    "pyyaml>=6.0",
    "gitpython>=3.1.0",
]

[project.scripts]
helios-mcp = "helios_mcp.server:main"

[project.entry-points.mcp_servers]
helios = "helios_mcp.server:create_server"

[project.urls]
Homepage = "https://github.com/yourusername/helios-mcp"
Repository = "https://github.com/yourusername/helios-mcp.git"
Issues = "https://github.com/yourusername/helios-mcp/issues"

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
]
```

### Required Fields (2025)
- `name` - **REQUIRED**: PyPI package name (only field that cannot be dynamic)
- `version` - **REQUIRED**: Package version
- `description` - **RECOMMENDED**: Short description for PyPI
- `readme` - **RECOMMENDED**: Path to README file
- `requires-python` - **RECOMMENDED**: Python version requirement
- `license` - **RECOMMENDED**: License information
- `authors` - **RECOMMENDED**: Package authors

## Authentication Setup

### PyPI API Token (Recommended)
```bash
# 1. Create PyPI account: https://pypi.org/account/register/
# 2. Generate API token: https://pypi.org/manage/account/token/
# 3. Set environment variable
export PYPI_TOKEN="pypi-AgEIcHlwaS..."

# 4. Use in publish command
uv publish --token $PYPI_TOKEN
```

### Environment Variables (Secure)
```bash
# Option 1: Token authentication
export UV_PUBLISH_TOKEN="pypi-AgEIcHlwaS..."
uv publish

# Option 2: Username/Password (deprecated)
export UV_PUBLISH_USERNAME="__token__"
export UV_PUBLISH_PASSWORD="pypi-AgEIcHlwaS..."
uv publish
```

## Publishing Workflow

### Step-by-Step Process
```bash
# 1. Ensure clean working directory
git status
git add .
git commit -m "Prepare for publishing"

# 2. Update version if needed
uv version --bump patch  # or minor, major

# 3. Build package
uv build
# Creates: dist/helios_mcp-0.1.0-py3-none-any.whl
#          dist/helios_mcp-0.1.0.tar.gz

# 4. Test build integrity
uv build --no-sources  # Ensures clean build

# 5. Test local installation
uv run --with ./dist/helios_mcp-0.1.0-py3-none-any.whl --no-project -- python -c "
import helios_mcp
print('Import successful!')
print(f'Version: {helios_mcp.__version__}')
"

# 6. Test on TestPyPI (RECOMMENDED)
uv publish --publish-url https://test.pypi.org/legacy/ --token $TESTPYPI_TOKEN

# 7. Test install from TestPyPI
pip install -i https://test.pypi.org/simple/ helios-mcp

# 8. Publish to PyPI
uv publish --token $PYPI_TOKEN

# 9. Test final installation
pip install helios-mcp
```

## Version Management

### UV Version Commands
```bash
# Set exact version
uv version 1.0.0

# Semantic version bumping
uv version --bump major    # 0.1.0 -> 1.0.0
uv version --bump minor    # 0.1.0 -> 0.2.0
uv version --bump patch    # 0.1.0 -> 0.1.1

# Pre-release versions
uv version --bump alpha    # 0.1.0 -> 0.1.0a1
uv version --bump beta     # 0.1.0 -> 0.1.0b1
uv version --bump rc       # 0.1.0 -> 0.1.0rc1
```

### Version Strategy
- **Development**: 0.1.0, 0.2.0, etc.
- **Alpha/Beta**: 0.1.0a1, 0.1.0b1
- **Release Candidates**: 0.1.0rc1
- **Stable**: 1.0.0, 1.1.0, etc.

## Testing Before Publishing

### Local Testing Methods
```bash
# Method 1: Direct wheel installation
uv build
pip install dist/helios_mcp-0.1.0-py3-none-any.whl

# Method 2: UV tool install (persistent)
uv tool install dist/helios_mcp-0.1.0-py3-none-any.whl

# Method 3: Ephemeral testing with uvx
uvx dist/helios_mcp-0.1.0-py3-none-any.whl --help

# Method 4: Test import without installation
uv run --with ./dist/helios_mcp-0.1.0-py3-none-any.whl --no-project -- python -c "import helios_mcp"
```

### TestPyPI Setup
```bash
# 1. Create TestPyPI account: https://test.pypi.org/account/register/
# 2. Generate token: https://test.pypi.org/manage/account/token/
export TESTPYPI_TOKEN="pypi-AgEIcHlwaS..."

# 3. Publish to TestPyPI
uv publish --publish-url https://test.pypi.org/legacy/ --token $TESTPYPI_TOKEN

# 4. Test installation from TestPyPI
pip install -i https://test.pypi.org/simple/ helios-mcp
```

## Build Configuration

### Build Options
```bash
# Build both wheel and source distribution (default)
uv build

# Build only wheel
uv build --wheel

# Build only source distribution
uv build --sdist

# Build from specific directory
uv build path/to/project

# Build specific package in workspace
uv build --package my-package

# Clean build without custom sources
uv build --no-sources
```

### Dist Directory Structure
```
dist/
├── helios_mcp-0.1.0-py3-none-any.whl  # Binary distribution
└── helios_mcp-0.1.0.tar.gz            # Source distribution
```

## Common Issues & Solutions

### Issue: Package name conflicts
**Solution**: Check PyPI for name availability, use underscores/hyphens appropriately
```bash
# Names are normalized: helios-mcp == helios_mcp == helios.mcp
```

### Issue: Build fails with missing dependencies
**Solution**: Check `[build-system]` requirements in pyproject.toml
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel", "your-build-deps"]
build-backend = "setuptools.build_meta"
```

### Issue: Import errors after installation
**Solution**: Verify package structure and entry points
```python
# src/helios_mcp/__init__.py must exist
__version__ = "0.1.0"
```

### Issue: Authentication failures
**Solution**: Use proper token format and environment variables
```bash
# Token must start with "pypi-" for main PyPI
export UV_PUBLISH_TOKEN="pypi-AgEIcHlwaS..."
```

### Issue: Version already exists on PyPI
**Solution**: Bump version before republishing
```bash
uv version --bump patch
uv build
uv publish --token $PYPI_TOKEN
```

## Security Best Practices

### Token Management
- **Per-project tokens**: Create specific tokens for each package
- **Environment variables**: Never put tokens in code or command history
- **Token rotation**: Regenerate tokens periodically
- **Scope limitation**: Use minimal required permissions

### Publishing Safety
```bash
# 1. Always test on TestPyPI first
uv publish --publish-url https://test.pypi.org/legacy/ --token $TESTPYPI_TOKEN

# 2. Verify build contents
tar -tzf dist/helios_mcp-0.1.0.tar.gz | head -20

# 3. Check wheel contents  
unzip -l dist/helios_mcp-0.1.0-py3-none-any.whl

# 4. Use --dry-run for testing (if available)
uv publish --dry-run
```

## FastMCP Specific Configuration

### Entry Points for MCP Servers
```toml
[project.entry-points.mcp_servers]
helios = "helios_mcp.server:create_server"

[project.scripts]
helios-mcp = "helios_mcp.server:main"
```

### FastMCP Dependencies
```toml
[project]
dependencies = [
    "fastmcp>=2.2.6",
    "pyyaml>=6.0",
    "gitpython>=3.1.0",
]
```

## Publishing Checklist

### Pre-Publishing
- [ ] All tests passing: `uv run pytest`
- [ ] Code linting clean: `uv run ruff check .`
- [ ] Version updated: `uv version --bump patch`
- [ ] pyproject.toml complete with required fields
- [ ] README.md exists and is informative
- [ ] License file included

### Publishing
- [ ] Build successful: `uv build`
- [ ] Local install test passes
- [ ] TestPyPI upload successful
- [ ] TestPyPI install test passes
- [ ] PyPI upload successful
- [ ] Final install test passes

### Post-Publishing
- [ ] Git tag created: `git tag v0.1.0`
- [ ] GitHub release created
- [ ] Installation instructions updated
- [ ] Documentation updated with new version

## Emergency Recovery

### If Wrong Version Published
```bash
# PyPI doesn't allow re-uploading same version
# Solution: Bump version and republish
uv version --bump patch
uv build
uv publish --token $PYPI_TOKEN
```

### If Package Broken
```bash
# 1. Yank the problematic version (doesn't delete, just warns users)
# Use PyPI web interface to yank version

# 2. Fix issues and publish new version
uv version --bump patch
# Fix the issues
uv build
uv publish --token $PYPI_TOKEN
```

## Today's Action Items

For helios-mcp publishing TODAY:

1. **Verify pyproject.toml** has all required fields
2. **Set up PyPI token**: `export PYPI_TOKEN="your-token"`
3. **Build**: `uv build`
4. **Test locally**: Install and import test
5. **TestPyPI**: Upload and test
6. **PyPI**: Final publish
7. **Verify**: `pip install helios-mcp` works

**Estimated Time**: 30-45 minutes for complete workflow

## References

- [UV Package Building Guide](https://docs.astral.sh/uv/guides/package/)
- [PyPI Publishing Documentation](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PEP 621 - pyproject.toml metadata](https://peps.python.org/pep-0621/)
- [PyPI Classifiers](https://pypi.org/classifiers/)