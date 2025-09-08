"""High-performance caching system for Helios MCP server.

Provides TTL-based caching with file modification time tracking,
memoization for inheritance calculations, and thread-safe operations.
"""

import asyncio
import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Callable, TypeVar
from functools import wraps
import weakref
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass(frozen=True)
class CacheKey:
    """Immutable cache key for file-based caching."""
    path: Path
    mtime: float
    size: int
    
    @classmethod
    def from_path(cls, path: Path) -> "CacheKey":
        """Create cache key from file path.
        
        Args:
            path: Path to file
            
        Returns:
            Cache key with file metadata
            
        Raises:
            OSError: If file doesn't exist or can't be accessed
        """
        try:
            stat = path.stat()
            return cls(
                path=path,
                mtime=stat.st_mtime,
                size=stat.st_size
            )
        except OSError as e:
            logger.warning(f"Failed to create cache key for {path}: {e}")
            raise


@dataclass
class CacheEntry:
    """Cache entry with TTL and access tracking."""
    value: Any
    created_at: float
    accessed_at: float
    access_count: int
    ttl: float
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl
    
    def touch(self) -> None:
        """Update access statistics."""
        self.accessed_at = time.time()
        self.access_count += 1


class PerformanceCache:
    """Thread-safe, TTL-based cache with file modification tracking.
    
    Features:
    - TTL-based expiration
    - File modification time invalidation
    - Thread-safe operations with minimal lock contention
    - LRU eviction with access frequency weighting
    - Memory usage limits
    - Performance metrics
    """
    
    def __init__(
        self,
        max_entries: int = 1000,
        default_ttl: float = 300.0,  # 5 minutes
        yaml_ttl: float = 60.0,      # 1 minute for YAML files
        inheritance_ttl: float = 180.0,  # 3 minutes for inheritance calculations
        max_memory_mb: float = 100.0,
        cleanup_interval: float = 30.0
    ) -> None:
        """Initialize performance cache.
        
        Args:
            max_entries: Maximum number of cache entries
            default_ttl: Default TTL in seconds
            yaml_ttl: TTL for YAML file contents
            inheritance_ttl: TTL for inheritance calculations
            max_memory_mb: Maximum memory usage in MB
            cleanup_interval: Cleanup interval in seconds
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._file_cache: Dict[CacheKey, Any] = {}
        self._lock = threading.RLock()
        
        # Configuration
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self.yaml_ttl = yaml_ttl
        self.inheritance_ttl = inheritance_ttl
        self.max_memory_mb = max_memory_mb
        self.cleanup_interval = cleanup_interval
        
        # Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.cleanup_runs = 0
        
        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # Weak references to avoid memory leaks
        self._instances = weakref.WeakSet()
        self._instances.add(self)
    
    async def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def shutdown(self) -> None:
        """Shutdown cache and cleanup resources."""
        self._shutdown = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self.clear()
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _estimate_size(self, obj: Any) -> int:
        """Estimate memory size of object in bytes."""
        try:
            import sys
            return sys.getsizeof(obj)
        except Exception:
            # Fallback estimation
            if isinstance(obj, str):
                return len(obj.encode('utf-8'))
            elif isinstance(obj, (list, tuple)):
                return sum(self._estimate_size(item) for item in obj)
            elif isinstance(obj, dict):
                return sum(
                    self._estimate_size(k) + self._estimate_size(v)
                    for k, v in obj.items()
                )
            else:
                return 1024  # Default estimate
    
    def _should_evict(self) -> bool:
        """Check if cache should evict entries."""
        if len(self._cache) >= self.max_entries:
            return True
        
        # Estimate total memory usage
        total_size = sum(
            self._estimate_size(entry.value)
            for entry in self._cache.values()
        )
        return total_size > self.max_memory_mb * 1024 * 1024
    
    def _evict_entries(self) -> None:
        """Evict least recently used entries."""
        if not self._cache:
            return
        
        # Sort by access frequency and recency (lower is better for eviction)
        entries = [
            (key, entry, entry.access_count / max(1, time.time() - entry.accessed_at))
            for key, entry in self._cache.items()
            if entry.is_expired() or len(self._cache) > self.max_entries // 2
        ]
        
        # Remove expired entries first
        expired = [(key, entry, score) for key, entry, score in entries if entry.is_expired()]
        if expired:
            for key, _, _ in expired:
                del self._cache[key]
                self.evictions += 1
        
        # If still over limit, remove least valuable entries
        if self._should_evict():
            remaining = [(key, entry, score) for key, entry, score in entries if not entry.is_expired()]
            remaining.sort(key=lambda x: x[2])  # Sort by access score
            
            # Remove bottom 25% of entries
            to_remove = remaining[:len(remaining) // 4]
            for key, _, _ in to_remove:
                if key in self._cache:
                    del self._cache[key]
                    self.evictions += 1
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.cleanup_interval)
                with self._lock:
                    self._evict_entries()
                    self.cleanup_runs += 1
                    
                    # Clean file cache
                    expired_files = [
                        key for key in self._file_cache.keys()
                        if not key.path.exists() or key != CacheKey.from_path(key.path)
                    ]
                    for key in expired_files:
                        del self._file_cache[key]
                        
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache.
        
        Args:
            key: Cache key
            default: Default value if not found
            
        Returns:
            Cached value or default
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self.misses += 1
                return default
            
            if entry.is_expired():
                del self._cache[key]
                self.misses += 1
                return default
            
            entry.touch()
            self.hits += 1
            return entry.value
    
    def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[float] = None
    ) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        if ttl is None:
            ttl = self.default_ttl
        
        with self._lock:
            now = time.time()
            self._cache[key] = CacheEntry(
                value=value,
                created_at=now,
                accessed_at=now,
                access_count=1,
                ttl=ttl
            )
            
            # Check if eviction needed
            if self._should_evict():
                self._evict_entries()
    
    def get_file_cached(
        self, 
        path: Path, 
        loader: Callable[[Path], T],
        ttl: Optional[float] = None
    ) -> T:
        """Get file contents with modification time caching.
        
        Args:
            path: File path
            loader: Function to load file contents
            ttl: Time to live for cache entry
            
        Returns:
            File contents (possibly cached)
        """
        try:
            cache_key = CacheKey.from_path(path)
        except OSError:
            # File doesn't exist or can't be accessed
            return loader(path)
        
        with self._lock:
            # Check file cache first
            cached_value = self._file_cache.get(cache_key)
            if cached_value is not None:
                self.hits += 1
                return cached_value
            
            # Load and cache
            value = loader(path)
            self._file_cache[cache_key] = value
            
            # Also add to main cache with TTL
            cache_key_str = f"file:{path}:{cache_key.mtime}"
            if ttl is None:
                ttl = self.yaml_ttl if path.suffix.lower() == '.yaml' else self.default_ttl
            self.set(cache_key_str, value, ttl)
            
            self.misses += 1
            return value
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._file_cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / max(1, total_requests)
            
            return {
                "entries": len(self._cache),
                "file_entries": len(self._file_cache),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "evictions": self.evictions,
                "cleanup_runs": self.cleanup_runs,
                "memory_estimate_mb": sum(
                    self._estimate_size(entry.value)
                    for entry in self._cache.values()
                ) / (1024 * 1024),
            }


# Global cache instance
_global_cache: Optional[PerformanceCache] = None


def get_cache() -> PerformanceCache:
    """Get global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = PerformanceCache()
    return _global_cache


def cached(
    ttl: Optional[float] = None,
    key_func: Optional[Callable[..., str]] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for caching function results.
    
    Args:
        ttl: Time to live in seconds
        key_func: Function to generate cache key from arguments
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache = get_cache()
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{cache._generate_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator


async def cached_async(
    ttl: Optional[float] = None,
    key_func: Optional[Callable[..., str]] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Async decorator for caching function results.
    
    Args:
        ttl: Time to live in seconds
        key_func: Function to generate cache key from arguments
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache = get_cache()
        
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{cache._generate_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator


async def init_cache() -> None:
    """Initialize global cache with background cleanup."""
    cache = get_cache()
    await cache.start_cleanup_task()


async def shutdown_cache() -> None:
    """Shutdown global cache."""
    global _global_cache
    if _global_cache:
        await _global_cache.shutdown()
        _global_cache = None
