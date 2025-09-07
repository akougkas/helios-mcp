"""Server lifecycle management for Helios MCP.

Provides graceful shutdown, health checks, auto-recovery, and resource cleanup
to ensure production reliability without crashes or incomplete operations.
"""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List
from contextlib import asynccontextmanager
import threading
from datetime import datetime, timedelta

from .git_store import GitStore
from .config import HeliosConfig
from .validation import ConfigValidator

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Manages server lifecycle with graceful shutdown and health monitoring.
    
    Features:
    - Signal handlers for SIGINT/SIGTERM
    - Periodic health checks of git repo and configs
    - Auto-recovery from transient failures
    - Ensures git operations complete before shutdown
    - Resource cleanup on exit
    """
    
    def __init__(
        self,
        helios_dir: Path,
        health_check_interval: float = 60.0,
        shutdown_timeout: float = 30.0,
        process_lock = None
    ):
        """
        Args:
            helios_dir: Path to Helios configuration directory
            health_check_interval: Seconds between health checks
            shutdown_timeout: Max seconds to wait for graceful shutdown
        """
        self.helios_dir = helios_dir
        self.health_check_interval = health_check_interval
        self.shutdown_timeout = shutdown_timeout
        
        # Core components
        self.config = HeliosConfig(
            base_path=helios_dir / "base",
            personas_path=helios_dir / "personas",
            learned_path=helios_dir / "learned",
            temporary_path=helios_dir / "temporary"
        )
        self.git_store = GitStore(helios_dir)
        
        # Lifecycle state
        self.is_running = False
        self.shutdown_requested = False
        self.pending_operations: List[asyncio.Task] = []
        self.health_task: Optional[asyncio.Task] = None
        
        # Resource tracking
        self.open_files: List[Any] = []
        self.cleanup_callbacks: List[Callable[[], None]] = []
        
        # Signal handlers registered flag
        self._signal_handlers_registered = False
        
        # Process lock and validator
        self.process_lock = process_lock
        self.validator = ConfigValidator(helios_dir)
    
    def register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        if self._signal_handlers_registered:
            return
            
        def signal_handler(signum: int, frame) -> None:
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self.shutdown_requested = True
            
            # Schedule async shutdown in event loop
            try:
                loop = asyncio.get_running_loop()
                if not loop.is_closed():
                    asyncio.create_task(self.shutdown())
            except RuntimeError:
                # No event loop running, shutdown will be handled elsewhere
                pass
        
        # Register for SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self._signal_handlers_registered = True
        logger.debug("Signal handlers registered for graceful shutdown")
    
    async def start(self) -> None:
        """Start the lifecycle manager."""
        if self.is_running:
            return
            
        logger.info("Starting Helios lifecycle manager")
        self.is_running = True
        self.shutdown_requested = False
        
        # Register signal handlers
        self.register_signal_handlers()
        
        # Ensure directories exist
        self.config.ensure_directories()
        
        # Perform initial health check
        health_status = await self.check_health()
        if not health_status["healthy"]:
            logger.warning(f"Initial health check failed: {health_status['issues']}")
            # Try auto-recovery
            if not await self.attempt_recovery():
                raise RuntimeError("Failed to initialize - health check failed")
        
        # Start health monitoring
        if self.health_check_interval > 0:
            self.health_task = asyncio.create_task(self._health_monitor())
            logger.debug(f"Health monitoring started (interval: {self.health_check_interval}s)")
        
        logger.info("Lifecycle manager started successfully")
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the lifecycle manager."""
        if not self.is_running or self.shutdown_requested:
            return
            
        logger.info("Beginning graceful shutdown")
        self.shutdown_requested = True
        
        try:
            # Stop health monitoring
            if self.health_task and not self.health_task.done():
                self.health_task.cancel()
                try:
                    await asyncio.wait_for(self.health_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Wait for pending operations to complete
            await self.complete_pending_operations()
            
            # Ensure any final git commits are completed
            await self.ensure_git_operations_complete()
            
            # Run cleanup callbacks
            await self.cleanup_resources()
            
            # Release process lock if we have one
            if self.process_lock:
                self.process_lock.release()
            
            self.is_running = False
            logger.info("Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            self.is_running = False
            raise
    
    async def check_health(self) -> Dict[str, Any]:
        """Comprehensive health check of Helios components."""
        issues = []
        
        try:
            # Check helios directory exists and is accessible
            if not self.helios_dir.exists():
                issues.append(f"Helios directory does not exist: {self.helios_dir}")
            elif not self.helios_dir.is_dir():
                issues.append(f"Helios path is not a directory: {self.helios_dir}")
            elif not os.access(self.helios_dir, os.R_OK | os.W_OK):
                issues.append(f"No read/write access to helios directory: {self.helios_dir}")
            
            # Check git repository health
            try:
                repo_status = self.git_store.get_repo_status()
                if "error" in repo_status:
                    issues.append(f"Git repository error: {repo_status['error']}")
            except Exception as e:
                issues.append(f"Git repository check failed: {e}")
            
            # Check configuration directories
            for dir_name, dir_path in [
                ("base", self.config.base_path),
                ("personas", self.config.personas_path),
                ("learned", self.config.learned_path),
                ("temporary", self.config.temporary_path)
            ]:
                if not dir_path.exists():
                    issues.append(f"Missing {dir_name} directory: {dir_path}")
                elif not os.access(dir_path, os.R_OK | os.W_OK):
                    issues.append(f"No access to {dir_name} directory: {dir_path}")
            
            # Validate configurations
            config_errors = self.validator.validate_all_configs(self.helios_dir)
            if config_errors:
                issues.extend([f"Config validation: {error}" for error in config_errors[:3]])  # Limit to first 3 errors
            
            return {
                "healthy": len(issues) == 0,
                "issues": issues,
                "timestamp": datetime.now().isoformat(),
                "helios_dir": str(self.helios_dir)
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "healthy": False,
                "issues": [f"Health check exception: {e}"],
                "timestamp": datetime.now().isoformat(),
                "helios_dir": str(self.helios_dir)
            }
    
    async def attempt_recovery(self) -> bool:
        """Attempt to recover from transient failures."""
        logger.info("Attempting auto-recovery")
        
        try:
            # Ensure directories exist
            self.config.ensure_directories()
            logger.debug("Configuration directories created/verified")
            
            # Try to reinitialize git repository if needed
            try:
                self.git_store = GitStore(self.helios_dir)
                logger.debug("Git repository reinitialized")
            except Exception as e:
                logger.warning(f"Git recovery failed: {e}")
                return False
            
            # Verify recovery with health check
            health_status = await self.check_health()
            if health_status["healthy"]:
                logger.info("Auto-recovery successful")
                return True
            else:
                logger.warning(f"Recovery incomplete - remaining issues: {health_status['issues']}")
                return False
                
        except Exception as e:
            logger.error(f"Recovery attempt failed: {e}")
            return False
    
    async def complete_pending_operations(self) -> None:
        """Wait for all pending operations to complete."""
        if not self.pending_operations:
            return
            
        logger.info(f"Waiting for {len(self.pending_operations)} pending operations to complete")
        
        try:
            # Wait for all pending operations with timeout
            await asyncio.wait_for(
                asyncio.gather(*self.pending_operations, return_exceptions=True),
                timeout=self.shutdown_timeout
            )
            logger.debug("All pending operations completed")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for operations - cancelling {len(self.pending_operations)} tasks")
            for task in self.pending_operations:
                if not task.done():
                    task.cancel()
        except Exception as e:
            logger.error(f"Error completing pending operations: {e}")
        finally:
            self.pending_operations.clear()
    
    async def ensure_git_operations_complete(self) -> None:
        """Ensure any git operations in progress are completed."""
        try:
            # Check if there are uncommitted changes and commit them
            if self.git_store.has_uncommitted_changes():
                logger.info("Committing final changes before shutdown")
                success = self.git_store.auto_commit("shutdown: final commit before server stop")
                if success:
                    logger.debug("Final changes committed successfully")
                else:
                    logger.warning("Failed to commit final changes")
            
        except Exception as e:
            logger.error(f"Error ensuring git operations complete: {e}")
    
    async def cleanup_resources(self) -> None:
        """Clean up all tracked resources."""
        logger.debug("Cleaning up resources")
        
        # Close any open files
        for file_handle in self.open_files:
            try:
                if hasattr(file_handle, 'close') and not file_handle.closed:
                    file_handle.close()
            except Exception as e:
                logger.warning(f"Error closing file handle: {e}")
        
        self.open_files.clear()
        
        # Run cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Error in cleanup callback: {e}")
        
        self.cleanup_callbacks.clear()
    
    def register_operation(self, task: asyncio.Task) -> None:
        """Register an operation that should complete before shutdown."""
        self.pending_operations.append(task)
        
        # Clean up completed tasks
        self.pending_operations = [t for t in self.pending_operations if not t.done()]
    
    def register_file(self, file_handle: Any) -> None:
        """Register a file handle for cleanup on shutdown."""
        self.open_files.append(file_handle)
    
    def register_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """Register a cleanup callback to run on shutdown."""
        self.cleanup_callbacks.append(callback)
        
        # Register process lock cleanup if we have one
        if self.process_lock and self.process_lock.release not in [cb.__func__ if hasattr(cb, '__func__') else cb for cb in self.cleanup_callbacks]:
            self.cleanup_callbacks.append(self.process_lock.release)
    
    async def _health_monitor(self) -> None:
        """Background task for periodic health monitoring."""
        logger.debug("Health monitoring task started")
        
        last_failure_time = None
        consecutive_failures = 0
        
        try:
            while self.is_running and not self.shutdown_requested:
                await asyncio.sleep(self.health_check_interval)
                
                if self.shutdown_requested:
                    break
                
                health_status = await self.check_health()
                
                if health_status["healthy"]:
                    if consecutive_failures > 0:
                        logger.info("Health check recovered after failure")
                        consecutive_failures = 0
                        last_failure_time = None
                else:
                    consecutive_failures += 1
                    current_time = datetime.now()
                    
                    if last_failure_time is None:
                        last_failure_time = current_time
                        logger.warning(f"Health check failed: {health_status['issues']}")
                    
                    # Try recovery after 2 consecutive failures
                    if consecutive_failures == 2:
                        logger.warning("Attempting auto-recovery after health check failures")
                        if await self.attempt_recovery():
                            consecutive_failures = 0
                            last_failure_time = None
                            logger.info("Auto-recovery successful")
                        else:
                            logger.error("Auto-recovery failed - manual intervention may be required")
                    
                    # Log ongoing failures
                    elif consecutive_failures > 2:
                        time_since_failure = current_time - last_failure_time
                        logger.error(
                            f"Health check failing for {time_since_failure.total_seconds():.0f}s "
                            f"({consecutive_failures} consecutive failures): {health_status['issues']}"
                        )
                
        except asyncio.CancelledError:
            logger.debug("Health monitoring task cancelled")
        except Exception as e:
            logger.error(f"Health monitoring task failed: {e}")


@asynccontextmanager
async def managed_lifecycle(
    helios_dir: Path,
    health_check_interval: float = 60.0,
    shutdown_timeout: float = 30.0,
    process_lock = None
):
    """Context manager for Helios lifecycle management.
    
    Usage:
        async with managed_lifecycle(helios_dir) as manager:
            # Your server code here
            await server.run()
    """
    manager = LifecycleManager(helios_dir, health_check_interval, shutdown_timeout, process_lock)
    
    try:
        await manager.start()
        yield manager
    finally:
        await manager.shutdown()
