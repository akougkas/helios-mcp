# Helios MCP Deployment Strategy

## Overview

This document outlines the deployment strategy for Helios MCP, focusing on installation detection, robust lifecycle management, and customer value delivery.

## Installation Detection Implementation

### Minimal Viable Approach (v0.1.0)

```python
# src/helios_mcp/bootstrap.py
from pathlib import Path
from datetime import datetime
import yaml

class BootstrapManager:
    """Manages first installation and subsequent boots."""
    
    VERSION_FILE = ".helios_version"
    
    def __init__(self, helios_dir: Path):
        self.helios_dir = helios_dir
        self.version_file = helios_dir / self.VERSION_FILE
    
    def is_first_install(self) -> bool:
        """Check if this is a fresh installation."""
        return not self.version_file.exists()
    
    def bootstrap_installation(self) -> None:
        """Initialize a fresh Helios installation."""
        # Create directory structure
        self.helios_dir.mkdir(parents=True, exist_ok=True)
        
        # Write version marker
        self.version_file.write_text(f"0.1.0\n{datetime.now().isoformat()}\n")
        
        # Create default base configuration
        base_dir = self.helios_dir / "base"
        base_dir.mkdir(exist_ok=True)
        
        default_config = {
            "base_importance": 0.7,
            "behaviors": {
                "communication_style": "helpful and technical",
                "problem_solving": "systematic and thorough",
                "learning_approach": "examples and patterns"
            },
            "metadata": {
                "created": datetime.now().isoformat(),
                "version": "0.1.0"
            }
        }
        
        # Use atomic write
        self._atomic_write_yaml(
            base_dir / "identity.yaml", 
            default_config
        )
        
        # Initialize git repository
        from helios_mcp.git_store import GitStore
        git_store = GitStore(self.helios_dir)
        git_store.auto_commit("Initial Helios installation")
        
        # Create welcome persona
        personas_dir = self.helios_dir / "personas"
        personas_dir.mkdir(exist_ok=True)
        
        welcome_persona = {
            "specialization_level": 1,
            "behaviors": {
                "greeting": "Welcome to Helios MCP!",
                "purpose": "I help manage your AI behavioral configurations."
            },
            "metadata": {
                "created": datetime.now().isoformat(),
                "description": "Default welcome persona"
            }
        }
        
        self._atomic_write_yaml(
            personas_dir / "welcome.yaml",
            welcome_persona
        )
    
    def _atomic_write_yaml(self, path: Path, data: dict) -> None:
        """Write YAML file atomically to prevent corruption."""
        import tempfile
        import os
        
        # Write to temp file in same directory (same filesystem)
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=path.stem,
            suffix='.tmp'
        )
        
        try:
            with os.fdopen(fd, 'w') as f:
                yaml.safe_dump(data, f, default_flow_style=False)
            
            # Atomic rename (POSIX compliant)
            Path(temp_path).replace(path)
        except:
            # Clean up temp file on error
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise
```

## Robustness Enhancements

### 1. Process Locking

```python
# src/helios_mcp/locking.py
import os
import time
from pathlib import Path
from datetime import datetime, timedelta

class ProcessLock:
    """Manages process-level locking to prevent corruption."""
    
    LOCK_FILE = ".helios.lock"
    STALE_THRESHOLD = timedelta(minutes=5)
    
    def __init__(self, helios_dir: Path):
        self.lock_path = helios_dir / self.LOCK_FILE
    
    def acquire(self) -> bool:
        """Acquire process lock, cleaning stale locks."""
        if self.lock_path.exists():
            if self._is_stale():
                self.lock_path.unlink()  # Clean stale lock
            else:
                # Check if process is actually running
                try:
                    pid = int(self.lock_path.read_text().split('\n')[0])
                    os.kill(pid, 0)  # Check if process exists
                    return False  # Process is running
                except (ProcessLookupError, ValueError):
                    self.lock_path.unlink()  # Dead process
        
        # Write our lock
        self.lock_path.write_text(
            f"{os.getpid()}\n{datetime.now().isoformat()}"
        )
        return True
    
    def release(self) -> None:
        """Release the lock if we own it."""
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text().split('\n')[0])
                if pid == os.getpid():
                    self.lock_path.unlink()
            except:
                pass  # Best effort
    
    def _is_stale(self) -> bool:
        """Check if lock is stale based on timestamp."""
        try:
            content = self.lock_path.read_text().split('\n')
            if len(content) > 1:
                timestamp = datetime.fromisoformat(content[1])
                age = datetime.now() - timestamp
                return age > self.STALE_THRESHOLD
        except:
            return True  # Corrupted lock is stale
        return False
```

### 2. Configuration Validation

```python
# src/helios_mcp/validation.py
from pathlib import Path
import yaml
from typing import Dict, Any, Optional

class ConfigValidator:
    """Validates configuration integrity."""
    
    def validate_yaml_file(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate YAML file syntax and structure."""
        if not path.exists():
            return False, f"File not found: {path}"
        
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            
            if not isinstance(data, dict):
                return False, "Root must be a dictionary"
            
            # Validate based on file type
            if "base" in str(path):
                return self._validate_base_config(data)
            elif "personas" in str(path):
                return self._validate_persona_config(data)
            
            return True, None
            
        except yaml.YAMLError as e:
            return False, f"YAML parse error: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def _validate_base_config(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate base configuration structure."""
        required = ["base_importance", "behaviors"]
        for field in required:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        if not 0.0 <= data["base_importance"] <= 1.0:
            return False, "base_importance must be between 0.0 and 1.0"
        
        return True, None
    
    def _validate_persona_config(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate persona configuration structure."""
        required = ["specialization_level", "behaviors"]
        for field in required:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        if not isinstance(data["specialization_level"], int) or data["specialization_level"] < 1:
            return False, "specialization_level must be integer >= 1"
        
        return True, None
```

## Customer Deployment Scenarios

### Scenario 1: Individual Developer

```bash
# Install
uvx install helios-mcp

# Configure Claude Desktop
# (Auto-detects on first run, creates ~/.helios)

# Use immediately
# Server bootstraps on first connection
```

### Scenario 2: Team Sharing

```bash
# Developer A creates personas
helios-mcp init
git init
git remote add origin git@github.com:team/helios-configs.git
git push

# Developer B clones
git clone git@github.com:team/helios-configs.git ~/.helios
helios-mcp validate  # Check integrity

# Both use same personas with local modifications
```

### Scenario 3: CI/CD Integration

```yaml
# .github/workflows/validate-helios.yml
name: Validate Helios Configs
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install Helios
        run: uvx install helios-mcp
      - name: Validate Configurations
        run: helios-mcp validate ./
      - name: Test Inheritance
        run: helios-mcp test-inheritance
```

## Recovery Strategies

### Corruption Recovery

```python
class RecoveryManager:
    """Handles recovery from various failure scenarios."""
    
    def recover_from_corruption(self, path: Path) -> bool:
        """Attempt to recover corrupted configuration."""
        backup_path = path.with_suffix('.backup')
        
        # Try backup first
        if backup_path.exists():
            try:
                # Validate backup
                validator = ConfigValidator()
                valid, error = validator.validate_yaml_file(backup_path)
                if valid:
                    backup_path.replace(path)
                    return True
            except:
                pass
        
        # Try git recovery
        try:
            git_store = GitStore(path.parent.parent)
            # Get last known good version from git
            content = git_store.get_file_at_commit(str(path), 'HEAD')
            path.write_text(content)
            return True
        except:
            pass
        
        # Last resort: create default
        if "base" in str(path):
            self._create_default_base(path)
            return True
        
        return False
```

## Implementation Priorities

### Phase 1: Critical (Before PyPI - 2 days)
1. ✅ Atomic file operations
2. ✅ Process locking
3. ✅ Installation detection
4. ✅ Basic validation

### Phase 2: Important (Week 1 - 5 days)
1. ⏳ Corruption recovery
2. ⏳ Migration system
3. ⏳ Enhanced diagnostics
4. ⏳ Backup strategy

### Phase 3: Nice-to-Have (Month 1)
1. 📋 Operation journaling
2. 📋 Telemetry (opt-in)
3. 📋 Web UI for management
4. 📋 Cloud sync option

## Success Metrics

### Technical Metrics
- Zero data loss incidents
- <100ms startup time
- <10MB memory footprint
- 100% recovery from crashes

### User Metrics
- Zero-config success rate: >95%
- Time to first value: <30 seconds
- Support tickets: <1% of users
- User retention: >80% after 30 days

## Risk Mitigation

### High Risk: Data Loss
- **Mitigation**: Atomic operations + Git versioning
- **Recovery**: Automatic from git history
- **Prevention**: Validation before writes

### Medium Risk: Concurrent Access
- **Mitigation**: Process locks with cleanup
- **Recovery**: Stale lock detection
- **Prevention**: Single instance enforcement

### Low Risk: Version Conflicts
- **Mitigation**: Semantic versioning
- **Recovery**: Migration system
- **Prevention**: Backward compatibility

## Conclusion

This deployment strategy ensures Helios MCP is:
1. **Robust**: Survives crashes, power loss, force quits
2. **Simple**: Zero-config for users
3. **Valuable**: Never loses user data
4. **Scalable**: From individual to enterprise

The phased approach allows shipping v0.1.0 quickly while building toward a production-grade v1.0.0.