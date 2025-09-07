# Helios MCP Architecture

## System Overview

Helios MCP is a behavioral configuration management system for AI agents that implements weighted inheritance patterns. It provides persistent personality layers that evolve through usage while maintaining core identity constraints.

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Desktop / Client                  │
└────────────────────┬───────────────────────────┬────────────┘
                     │ MCP Protocol (STDIO)      │
┌────────────────────▼───────────────────────────▼────────────┐
│                      Helios MCP Server                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  FastMCP Framework                   │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │    │
│  │  │   Tools   │ │Resources │ │     Prompts      │   │    │
│  │  └──────────┘ └──────────┘ └──────────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Inheritance Engine                      │    │
│  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐   │    │
│  │  │Calculator  │ │  Merger    │ │  Validator   │   │    │
│  │  └────────────┘ └────────────┘ └──────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Persistence Layer                       │    │
│  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐   │    │
│  │  │ConfigLoader│ │  GitStore  │ │ AtomicOps    │   │    │
│  │  └────────────┘ └────────────┘ └──────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
                     │                           │
┌────────────────────▼───────────────────────────▼────────────┐
│                    ~/.helios/ (Filesystem)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │   base/  │ │personas/ │ │ learned/ │ │  temporary/  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
│                         Git Repository                       │
└──────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. MCP Interface Layer

**Purpose**: Bridges AI agents with Helios configuration system via Model Context Protocol.

**Components**:
- **FastMCP Server** (`server.py`): Handles MCP protocol communication
- **Tool Handlers**: Expose configuration operations as MCP tools
- **Resource Providers**: Serve configuration data as MCP resources
- **Prompt Templates**: Provide behavioral guidance patterns

**Design Principles**:
- Stateless request handling (ephemeral process model)
- JSON-RPC 2.0 message format
- STDIO transport for process isolation

### 2. Inheritance Engine

**Purpose**: Implements the weighted behavioral inheritance model that defines Helios.

**Core Formula**:
```python
inheritance_weight = base_importance / (specialization_level ** 2)
final_behavior = base * weight + persona * (1 - weight)
```

**Components**:

#### InheritanceCalculator (`inheritance.py`)
- Computes inheritance weights based on specialization level
- Enforces weight bounds (0.01 - 1.0)
- Validates input parameters

#### BehaviorMerger (`inheritance.py`)
- Deep merges configuration hierarchies
- Handles type-aware merging (numeric averaging, string selection, list concatenation)
- Preserves metadata during merge operations

#### ConfigValidator (`validation.py`)
- Schema validation for configurations
- Type checking and range validation
- Recovery orchestration from corruption

### 3. Persistence Layer

**Purpose**: Ensures data durability and consistency across ephemeral process lifecycles.

**Components**:

#### ConfigLoader (`config.py`)
- YAML configuration management
- Directory structure maintenance
- Lazy loading with caching

#### GitStore (`git_store.py`)
- Automatic version control for all changes
- Commit automation with semantic messages
- History-based recovery capabilities

#### AtomicOps (`atomic_ops.py`)
- Crash-safe file operations
- Temp-file + atomic-rename pattern
- Cross-platform compatibility

### 4. Lifecycle Management

**Purpose**: Orchestrates server lifecycle, health monitoring, and graceful shutdown.

**Components**:

#### LifecycleManager (`lifecycle.py`)
- Signal handling (SIGINT/SIGTERM)
- Health monitoring with auto-recovery
- Resource cleanup on shutdown
- Pending operation tracking

#### ProcessLock (`locking.py`)
- Single-instance enforcement
- Atomic lock acquisition (O_EXCL)
- Stale lock detection and cleanup
- JSON-based lock metadata

#### BootstrapManager (`bootstrap.py`)
- First-installation detection
- Default configuration creation
- Directory structure initialization
- Version tracking

## Data Architecture

### Configuration Hierarchy

```yaml
~/.helios/
├── .helios_version          # Installation metadata
├── .helios.lock            # Process lock file
├── .git/                   # Version control
│
├── base/                   # Core identity layer
│   └── identity.yaml       # Base configuration
│       base_importance: 0.7
│       behaviors: {...}
│
├── personas/              # Specialized personalities
│   ├── researcher.yaml    # Domain-specific persona
│   │   specialization_level: 2
│   │   behaviors: {...}
│   └── coder.yaml
│       specialization_level: 3
│       behaviors: {...}
│
├── learned/              # Emergent patterns (future)
│   └── patterns.yaml     # Learned behaviors
│
└── temporary/           # Session overrides (future)
    └── session.yaml     # Temporary modifications
```

### Inheritance Flow

```
1. Load base configuration (foundation layer)
2. Load active persona (specialization layer)
3. Calculate inheritance weight (formula)
4. Merge behaviors (weighted combination)
5. Apply learned patterns (future: adaptation layer)
6. Apply temporary overrides (future: session layer)
```

## Design Patterns

### Ephemeral Process Pattern
**Problem**: MCP servers spawn per connection and die on disconnect.
**Solution**: Treat processes as stateless; persist all state to filesystem with git versioning.

### Atomic Operations Pattern
**Problem**: File corruption during crashes or concurrent access.
**Solution**: Write to temp file, then atomic rename to target.

### Factory Pattern
**Usage**: `create_server()` factory for FastMCP instance creation.
**Benefit**: Centralized configuration and dependency injection.

### Context Manager Pattern
**Usage**: Lock acquisition, lifecycle management.
**Benefit**: Guaranteed resource cleanup even on exceptions.

### Strategy Pattern
**Usage**: Recovery strategies in validation.
**Benefit**: Pluggable recovery mechanisms.

## Extension Points

### Adding New Tools

```python
@mcp.tool(
    description="Your tool description",
    parameters=YourParamsModel
)
async def your_tool(params: YourParamsModel, ctx: Context) -> dict:
    """Tool implementation."""
    return {"status": "success", "data": ...}
```

### Custom Personas

Create YAML in `~/.helios/personas/`:
```yaml
specialization_level: 2  # Higher = more specialized
behaviors:
  communication_style: "academic"
  problem_solving: "theoretical"
  preferred_frameworks: ["pytorch", "jax"]
metadata:
  created: "2025-09-07"
  author: "user"
```

### Recovery Strategies

Implement custom recovery in `ConfigValidator`:
```python
def recover_custom(self, path: Path) -> bool:
    # Your recovery logic
    return success
```

## Security Considerations

### Process Isolation
- Each MCP connection gets separate process
- No shared memory between connections
- Clean state per session

### File System Security
- Lock files prevent concurrent modification
- Atomic operations prevent partial writes
- Git provides audit trail

### Input Validation
- Schema validation on all configurations
- Parameter bounds checking
- Type enforcement

## Performance Characteristics

### Startup Time
- First run: ~500ms (bootstrap + git init)
- Subsequent: ~100ms (validation only)

### Memory Footprint
- Base: ~30MB Python runtime
- Active: ~50MB with configurations loaded
- Peak: ~100MB during merge operations

### Scalability Limits
- Personas: Unlimited (filesystem bound)
- Config size: ~10MB practical limit
- History: Git compression handles thousands of commits

## Error Handling Philosophy

### Fail-Safe Defaults
1. Validate configuration
2. Attempt git recovery if invalid
3. Create defaults if recovery fails
4. Always start with valid state

### Graceful Degradation
- Missing personas → Use base configuration
- Corrupted YAML → Restore from git
- Git failure → Use defaults
- Lock conflict → Clear message to user

## Learning System Architecture (v0.3.0)

### Design Philosophy
**Learning = Direct configuration editing + Git versioning**

No separate learning infrastructure. Learning tools are just convenient ways to edit persona/base configurations, with git providing complete history and revert capability.

### Learning Tools (4 new, total 11)

```python
@mcp.tool
async def learn_behavior(persona: str, key: str, value: Any) -> dict:
    """Add or update a behavior in a persona configuration."""
    # Directly edits ~/.helios/personas/{persona}.yaml
    # Git commit: "Learned: {key} for {persona}"

@mcp.tool
async def tune_weight(target: str, parameter: str, value: float) -> dict:
    """Adjust inheritance weights (base_importance, specialization_level)."""
    # Edits base/identity.yaml or personas/{name}.yaml
    # Git commit: "Tuned: {parameter} to {value}"

@mcp.tool
async def revert_learning(commits_back: int = 1) -> dict:
    """Undo recent learning by reverting git commits."""
    # Git revert HEAD~{commits_back}
    # Returns what was reverted

@mcp.tool
async def evolve_behavior(from_config: str, to_config: str, key: str) -> dict:
    """Move a learned behavior between configurations."""
    # Promotes behaviors from persona→base or base→persona
    # Git commit: "Evolved: {key} from {from_config} to {to_config}"
```

### How Learning Works

1. **Direct Editing**: All learning directly modifies YAML files
2. **Git Tracking**: Every learn operation creates a semantic commit
3. **Natural Evolution**: Personas evolve through actual usage
4. **Simple Reversion**: Undo any learning with git revert

### Example Learning Flow

```yaml
# Initial: ~/.helios/personas/developer.yaml
specialization_level: 2
behaviors:
  tools: ["pytest", "pip"]

# After: /learn developer tools.package_manager "uv"
specialization_level: 2
behaviors:
  tools: ["pytest", "pip"]
  package_manager: "uv"  # Added by learning

# Git log shows:
commit abc123: "Learned: package_manager=uv for developer"

# Can revert with: /revert 1
# Returns to original state via git
```

### Benefits of This Approach

- **Simplicity**: No separate learning system to maintain
- **Transparency**: Git diff shows exactly what was learned
- **Flexibility**: Can edit any part of any configuration
- **History**: Complete learning history in git log
- **Rollback**: Revert any learning, anytime
- **No overhead**: Reuses existing config and git infrastructure

## Future Architecture Considerations

### Distributed Personas (v0.4.0)
- Shared persona repositories
- Team synchronization
- Conflict resolution

### Plugin System (v0.5.0)
- Custom tool loading
- Behavior extensions
- Third-party integrations

## Architectural Invariants

1. **Process Ephemeral, Data Persistent**: Processes die, data lives in git
2. **No Corruption Possible**: Atomic operations or rollback
3. **Always Bootable**: System must start even with corrupted state
4. **Git as Truth**: Version control is source of truth
5. **Inheritance Always Applied**: No direct persona access without base

## Development Guidelines

### Code Organization
```
src/helios_mcp/
├── Core MCP Interface
│   ├── server.py         # FastMCP server setup
│   ├── cli.py           # Entry point and CLI
│   └── lifecycle.py     # Process lifecycle
│
├── Inheritance Engine
│   ├── inheritance.py   # Calculator and merger
│   └── validation.py    # Schema validation
│
├── Persistence Layer
│   ├── config.py        # Configuration loader
│   ├── git_store.py     # Git operations
│   └── atomic_ops.py    # Atomic file ops
│
└── Infrastructure
    ├── bootstrap.py     # First-run setup
    └── locking.py       # Process locking
```

### Testing Strategy
- Unit tests for each component
- Integration tests for tool chains
- Mock external dependencies (git, filesystem)
- Property-based testing for inheritance formula

### Deployment Model
```
pip install helios-mcp
    ↓
uvx helios-mcp
    ↓
Claude Desktop connects
    ↓
Process spawned (STDIO)
    ↓
Helios serves configuration
    ↓
Process dies on disconnect
```

This architecture enables Helios to provide robust, evolvable AI personalities while maintaining simplicity, reliability, and extensibility.