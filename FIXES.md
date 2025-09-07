# FIXES.md - Critical Issues for Next Session

## ✅ Working
- CLI imports work correctly
- Server bootstraps successfully 
- Basic logging and configuration loading
- 111/116 tests passing (96% success rate)

## 🔴 Critical Bugs Found

### 1. Asyncio Runtime Error (BLOCKING)
- **File**: `src/helios_mcp/cli.py` 
- **Error**: "Already running asyncio in this thread"
- **Impact**: Server crashes immediately on startup
- **Fix needed**: Fix asyncio event loop management in CLI

### 2. Lock Mechanism Not Working
- **File**: `src/helios_mcp/locking.py`
- **Issue**: Multiple instances can start in same directory
- **Root cause**: First server crashes, releasing lock immediately
- **Fix needed**: Fix asyncio issue first, then verify lock works

### 3. Missing Method in Validation
- **File**: `src/helios_mcp/validation.py`
- **Error**: `'ConfigValidator' object has no attribute 'validate_yaml_file'`
- **Impact**: 3 validation tests fail
- **Fix needed**: Add missing `validate_yaml_file` method or update tests to use `validate_yaml_syntax`

### 4. Missing Import in Tests
- **File**: `tests/test_validation.py`
- **Error**: `module 'helios_mcp.validation' does not have the attribute 'GitStore'`
- **Impact**: 1 test fails due to incorrect mock target
- **Fix needed**: Fix import path in test mocks

### 5. Git Recovery Logic Bug
- **File**: `src/helios_mcp/validation.py`
- **Issue**: `recover_from_corruption` returns False instead of True for missing files
- **Impact**: 1 test fails
- **Fix needed**: Review recovery logic for non-git environments

## 🟡 Warnings (Non-blocking)
- Coroutine warnings in CLI tests (3 warnings about unawaited coroutines)

## Next Session Priority
1. **CRITICAL**: Fix asyncio event loop issue in CLI (blocks all functionality)
2. **HIGH**: Fix validation method naming mismatch  
3. **MEDIUM**: Fix git recovery logic and test mocks
4. **VERIFY**: Test lock mechanism after asyncio fix

## Quick Test Commands
```bash
# Asyncio issue reproduction
timeout 5 uv run helios-mcp --helios-dir /tmp/test-async

# Validation tests
uv run pytest tests/test_validation.py -v

# Full test suite
uv run pytest --tb=no -q

# Lock test (after asyncio fix)
# Start server 1: uv run helios-mcp --helios-dir /tmp/lock-test &
# Start server 2: uv run helios-mcp --helios-dir /tmp/lock-test
```

## Estimated Fix Time
- Asyncio fix: 15-30 minutes
- Validation fixes: 10-15 minutes  
- Test suite: 100% passing target
- Total: 1 hour to fully working state