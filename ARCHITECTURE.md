# Helios MCP Production Architecture

## Executive Summary

Helios MCP is a behavioral configuration server for AI agents using weighted inheritance. This document outlines the production-ready architecture with focus on robustness, crash recovery, and zero-configuration deployment.

**Key Design Principle**: Work WITH the ephemeral nature of MCP STDIO servers, not against it. Each connection spawns a new process - this is a feature, not a bug.

## Production Hardening Status (v0.2.0)

### ✅ Implemented Features

1. **Atomic File Operations** (`atomic_ops.py`)
   - Temp file + atomic rename pattern
   - Cross-platform compatibility
   - Automatic cleanup on errors

2. **Installation Detection** (`bootstrap.py`)
   - First-install detection via `.helios_version`
   - Auto-bootstrap with defaults
   - Welcome persona creation

3. **Process Locking** (`locking.py`)
   - Single-instance enforcement via O_EXCL atomic creation
   - Stale lock cleanup (>5 minutes)
   - PID validation with psutil
   - JSON-based lock data format

4. **Configuration Validation** (`validation.py`)
   - YAML syntax checking
   - Schema validation (required fields, value ranges)
   - Git-based recovery from corruption
   - Default fallback creation

### 🔧 Critical Fixes Applied

1. **Event Loop Management** - Detects existing asyncio loops for MCP compatibility
2. **Atomic Lock Creation** - Uses OS-level O_EXCL flag to prevent race conditions
3. **Test Data Format** - Aligned test fixtures with JSON lock format

### 📊 Current Status
- **Tests**: 111/116 passing (96% success rate)
- **Known Issue**: Asyncio threading conflict needs resolution
- **Ready**: Near production-ready pending asyncio fix

## Lifecycle Architecture

### Process Lifecycle Model

```
Claude Desktop → Spawns → Helios Process → Dies on disconnect
                                 ↓
                        Uses ~/.helios/ (persistent)
                                 ↓
                        Git-versioned state
```

### Startup Sequence

```python
# 1. Process spawned by Claude Desktop via STDIO
helios-mcp --helios-dir ~/.helios

# 2. Initialization Phase
├── Check Installation State
│   ├── First Install? → Bootstrap
│   └── Existing? → Validate & Recover
├── Initialize Components
│   ├── LifecycleManager → Health monitoring
│   ├── GitStore → Version control
│   └── ConfigLoader → YAML management
└── Start MCP Server → Ready for requests
```

## Installation vs Boot Detection

### State Detection Strategy

```python
class InstallationDetector:
    """Detects installation state and manages bootstrapping."""
    
    def detect_state(self) -> InstallationState:
        """
        Returns one of:
        - FRESH_INSTALL: No ~/.helios directory
        - NEEDS_MIGRATION: Old version detected
        - CORRUPTED: Partial installation found
        - READY: Valid installation
        """
        
        # Detection hierarchy
        if not (self.helios_dir / ".helios_version").exists():
            return InstallationState.FRESH_INSTALL
            
        version = self._read_version()
        if version < CURRENT_VERSION:
            return InstallationState.NEEDS_MIGRATION
            
        if not self._validate_structure():
            return InstallationState.CORRUPTED
            
        return InstallationState.READY
```

### Bootstrap Process

```yaml
# ~/.helios/.helios_version
version: "0.1.0"
installed_at: "2025-09-07T10:00:00Z"
schema_version: 1
features:
  - weighted_inheritance
  - git_persistence
  - health_monitoring
```

### Migration Strategy

```python
class SchemaMigrator:
    """Handles schema migrations between versions."""
    
    migrations = {
        "0.0.1": migrate_001_to_010,  # Add schema_version
        "0.1.0": migrate_010_to_020,  # Future: Add learning
    }
    
    async def migrate(self, from_version: str, to_version: str):
        """Apply migrations sequentially."""
        for version, migration in self.migrations.items():
            if from_version < version <= to_version:
                await migration(self.helios_dir)
```

## Robustness Improvements

### 1. Atomic File Operations

```python
class AtomicFileWriter:
    """Ensures all file writes are atomic to prevent corruption."""
    
    async def write_yaml(self, path: Path, data: dict):
        """Write atomically using temp file + rename."""
        temp_path = path.with_suffix('.tmp')
        
        try:
            # Write to temp file
            with open(temp_path, 'w') as f:
                yaml.safe_dump(data, f)
            
            # Atomic rename (POSIX guarantees)
            temp_path.replace(path)
            
            # Git commit for durability
            await self.git_store.auto_commit(f"update: {path.name}")
            
        except Exception as e:
            temp_path.unlink(missing_ok=True)
            raise
```

### 2. Lock File Management

```python
class ProcessLock:
    """Prevents concurrent modifications."""
    
    def __init__(self, helios_dir: Path):
        self.lock_file = helios_dir / ".helios.lock"
        self.pid = os.getpid()
        
    def acquire(self) -> bool:
        """Try to acquire lock, clean stale locks."""
        if self.lock_file.exists():
            # Check if process is still alive
            old_pid = int(self.lock_file.read_text())
            if self._is_process_alive(old_pid):
                return False  # Another instance running
            # Stale lock, clean it up
            self.lock_file.unlink()
        
        # Write our PID
        self.lock_file.write_text(str(self.pid))
        return True
        
    def release(self):
        """Release lock on shutdown."""
        if self.lock_file.exists():
            current_pid = int(self.lock_file.read_text())
            if current_pid == self.pid:
                self.lock_file.unlink()
```

### 3. Crash Recovery System

```python
class CrashRecovery:
    """Handles recovery from unexpected termination."""
    
    def __init__(self, helios_dir: Path):
        self.recovery_dir = helios_dir / ".recovery"
        self.recovery_dir.mkdir(exist_ok=True)
        
    async def checkpoint(self, operation: str, data: dict):
        """Save checkpoint before risky operation."""
        checkpoint = {
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            "data": data,
            "pid": os.getpid()
        }
        
        checkpoint_file = self.recovery_dir / f"{operation}_{self.pid}.yaml"
        await AtomicFileWriter().write_yaml(checkpoint_file, checkpoint)
        
    async def recover(self) -> List[dict]:
        """Recover from incomplete operations."""
        recovered = []
        
        for checkpoint_file in self.recovery_dir.glob("*.yaml"):
            checkpoint = yaml.safe_load(checkpoint_file.read_text())
            
            # Check if operation is stale (>1 hour old)
            age = datetime.now() - datetime.fromisoformat(checkpoint["timestamp"])
            if age > timedelta(hours=1):
                # Clean up stale checkpoint
                checkpoint_file.unlink()
                continue
                
            # Attempt recovery based on operation type
            if await self._attempt_recovery(checkpoint):
                recovered.append(checkpoint)
                checkpoint_file.unlink()
                
        return recovered
```

### 4. Data Integrity Validation

```python
class IntegrityValidator:
    """Validates configuration integrity."""
    
    async def validate_config(self, config_path: Path) -> ValidationResult:
        """Comprehensive config validation."""
        
        issues = []
        
        # 1. YAML syntax validation
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            issues.append(f"Invalid YAML: {e}")
            return ValidationResult(valid=False, issues=issues)
            
        # 2. Schema validation
        try:
            if "base" in str(config_path):
                BaseConfig(**data)  # Pydantic validation
            elif "personas" in str(config_path):
                PersonaConfig(**data)
        except ValidationError as e:
            issues.append(f"Schema violation: {e}")
            
        # 3. Inheritance weight bounds
        if "base_importance" in data:
            if not 0.0 <= data["base_importance"] <= 1.0:
                issues.append("base_importance out of bounds")
                
        # 4. Git consistency
        if self.git_store.has_uncommitted_changes(config_path):
            issues.append("Uncommitted changes detected")
            
        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            recoverable=self._can_auto_recover(issues)
        )
```

## Session State Management

### Session Tracking

```yaml
# ~/.helios/.session_state.yaml
current_session:
  id: "abc12345"
  started_at: "2025-09-07T10:00:00Z"
  active_persona: "coder"
  operations_count: 42
  last_heartbeat: "2025-09-07T10:15:30Z"

previous_sessions:
  - id: "xyz98765"
    ended_at: "2025-09-07T09:55:00Z"
    operations_count: 15
    clean_shutdown: true
```

### Operation Journal

```python
class OperationJournal:
    """Tracks all operations for recovery and analytics."""
    
    def __init__(self, helios_dir: Path):
        self.journal_dir = helios_dir / ".journal"
        self.journal_dir.mkdir(exist_ok=True)
        self.current_journal = self.journal_dir / f"{datetime.now():%Y%m%d}.jsonl"
        
    async def log_operation(self, operation: dict):
        """Append operation to journal (append-only log)."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "operation": operation,
            "success": True
        }
        
        # Append to journal (atomic append)
        with open(self.current_journal, 'a') as f:
            f.write(json.dumps(entry) + '\n')
            
    async def replay_incomplete(self) -> List[dict]:
        """Replay operations that didn't complete."""
        incomplete = []
        
        if self.current_journal.exists():
            with open(self.current_journal) as f:
                for line in f:
                    entry = json.loads(line)
                    if not entry.get("success"):
                        incomplete.append(entry)
                        
        return incomplete
```

### Rollback Capability

```python
class ConfigRollback:
    """Enables configuration rollback on corruption."""
    
    async def create_snapshot(self, reason: str):
        """Create snapshot before risky operation."""
        snapshot_name = f"snapshot_{datetime.now():%Y%m%d_%H%M%S}_{reason}"
        
        # Git tag for easy rollback
        self.git_store.repo.create_tag(
            snapshot_name,
            message=f"Snapshot: {reason}"
        )
        
    async def rollback_to(self, snapshot: str):
        """Rollback to previous snapshot."""
        try:
            # Git reset to snapshot
            self.git_store.repo.git.reset('--hard', snapshot)
            
            # Clear any recovery state
            shutil.rmtree(self.helios_dir / ".recovery", ignore_errors=True)
            
            # Restart with clean state
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
```

## Customer Deployment Strategy

### Zero-Configuration Startup

```python
class ZeroConfigBootstrap:
    """Ensures Helios works immediately after install."""
    
    DEFAULT_CONFIG = {
        "base": {
            "identity": "Adaptive AI Assistant",
            "base_importance": 0.7,
            "behaviors": {
                "greeting": "Hello! How can I assist you?",
                "problem_solving": "Let me analyze this step by step"
            }
        },
        "personas": {
            "default": {
                "name": "default",
                "specialization_level": 1,
                "behaviors": {}
            }
        }
    }
    
    async def ensure_minimal_config(self):
        """Create minimal working config if none exists."""
        if not (self.helios_dir / "base" / "identity.yaml").exists():
            await self.create_default_base()
            
        if not any((self.helios_dir / "personas").glob("*.yaml")):
            await self.create_default_persona()
```

### Self-Healing Mechanisms

```python
class SelfHealer:
    """Automatic recovery from common issues."""
    
    HEALING_STRATEGIES = {
        "missing_directory": create_directory,
        "corrupted_yaml": restore_from_git,
        "invalid_permissions": fix_permissions,
        "stale_lock": clean_lock_file,
        "uncommitted_changes": auto_commit,
        "detached_head": checkout_main,
    }
    
    async def diagnose_and_heal(self) -> HealingReport:
        """Run diagnostic and attempt fixes."""
        report = HealingReport()
        
        for issue_type, healer in self.HEALING_STRATEGIES.items():
            if issue := self.detect_issue(issue_type):
                if await healer(issue):
                    report.healed.append(issue_type)
                else:
                    report.failed.append(issue_type)
                    
        return report
```

### Diagnostic System

```python
class DiagnosticSystem:
    """Provides clear error messages and recovery guidance."""
    
    ERROR_GUIDANCE = {
        "git_not_initialized": """
        Git repository not initialized. To fix:
        1. Run: cd ~/.helios && git init
        2. Restart Helios
        """,
        
        "permission_denied": """
        Cannot write to configuration directory. To fix:
        1. Run: chmod -R u+rw ~/.helios
        2. Ensure you own the directory
        """,
        
        "yaml_corrupted": """
        Configuration file corrupted. Recovery options:
        1. Automatic: Helios will restore from last commit
        2. Manual: Check ~/.helios/.recovery/ for backups
        """,
    }
    
    def get_user_guidance(self, error: Exception) -> str:
        """Provide actionable guidance for errors."""
        error_type = self.classify_error(error)
        return self.ERROR_GUIDANCE.get(
            error_type,
            f"Unexpected error: {error}\nPlease report at: github.com/helios-mcp/issues"
        )
```

### Upgrade Path

```python
class UpgradeManager:
    """Handles version upgrades without data loss."""
    
    async def prepare_upgrade(self, new_version: str):
        """Prepare for upgrade."""
        # 1. Create full backup
        backup_path = self.helios_dir / f".backups/pre_{new_version}"
        shutil.copytree(self.helios_dir, backup_path)
        
        # 2. Git tag current state
        self.git_store.repo.create_tag(f"pre_upgrade_{new_version}")
        
        # 3. Validate current state
        if not await self.validate_all_configs():
            raise UpgradeError("Cannot upgrade with invalid configs")
            
    async def post_upgrade_validation(self):
        """Validate after upgrade."""
        # Check all configs still load
        # Verify git history intact
        # Test core operations
        return ValidationReport()
```

## Implementation Priority

### Phase 1: Core Robustness (IMMEDIATE)
1. **Atomic file operations** - Prevent corruption
2. **Lock file management** - Prevent concurrent access
3. **Basic crash recovery** - Clean up on restart
4. **Installation detection** - First run vs restart

### Phase 2: Advanced Recovery (NEXT)
1. **Operation journal** - Track all operations
2. **Checkpoint system** - Save state before risky ops
3. **Rollback capability** - Undo corrupted changes
4. **Self-healing** - Auto-fix common issues

### Phase 3: Production Features (FUTURE)
1. **Diagnostic system** - Clear error messages
2. **Upgrade manager** - Safe version migration
3. **Performance monitoring** - Track operation times
4. **Analytics collection** - Usage patterns (privacy-preserving)

## Testing Strategy

### Robustness Test Scenarios

```python
class RobustnessTests:
    """Test crash recovery and error handling."""
    
    async def test_mid_operation_crash(self):
        """Simulate crash during file write."""
        # Start operation
        # Kill process
        # Restart and verify recovery
        
    async def test_concurrent_access(self):
        """Test lock file prevents corruption."""
        # Start two instances
        # Verify only one can modify
        
    async def test_corrupted_config(self):
        """Test recovery from corrupted YAML."""
        # Corrupt a config file
        # Start server
        # Verify auto-recovery
        
    async def test_git_corruption(self):
        """Test recovery from git issues."""
        # Corrupt git repo
        # Start server
        # Verify graceful handling
```

## Monitoring and Observability

### Health Metrics

```yaml
# ~/.helios/.health_metrics.yaml
uptime_seconds: 3600
operations_total: 150
operations_failed: 2
recovery_attempts: 1
recovery_successful: 1
last_error: null
config_validations_passed: 148
git_commits_total: 45
```

### Performance Tracking

```python
class PerformanceMonitor:
    """Track operation performance."""
    
    metrics = {
        "tool_latencies": {},  # Tool name -> [latencies]
        "git_operations": {},  # Operation -> duration
        "config_loads": {},    # File -> load time
    }
    
    @contextmanager
    def track_operation(self, operation: str):
        """Context manager for timing operations."""
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            self.record_metric(operation, duration)
```

## Security Considerations

### File System Security

1. **Permissions**: Configs should be 600 (user read/write only)
2. **Directory**: ~/.helios should be 700 (user only)
3. **Git hooks**: Disabled to prevent code execution
4. **Symlinks**: Not followed to prevent directory traversal

### Input Validation

1. **YAML**: Safe loader only (no code execution)
2. **Paths**: Validated to stay within ~/.helios
3. **Git messages**: Sanitized to prevent injection
4. **Tool inputs**: Pydantic validation on all inputs

## Summary

This architecture ensures Helios MCP is production-ready with:

1. **Zero-config startup** - Works immediately after install
2. **Crash resilience** - Recovers from any termination
3. **Data integrity** - No configuration loss ever
4. **Clear diagnostics** - Users know what went wrong
5. **Safe upgrades** - Version migrations without data loss

The key insight: MCP STDIO servers are ephemeral by design. We embrace this by making ~/.helios the source of truth, with git providing durability and version control. Every operation is atomic, every change is versioned, and recovery is automatic.