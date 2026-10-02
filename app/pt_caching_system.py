"""
PowerTrader AI+ Caching System
High-performance caching with TTL, memory management, and persistence
"""

import json
import os
import pickle
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable
import hashlib
import weakref
import gc


@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int
    ttl_seconds: Optional[float] = None
    size_bytes: int = 0
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def update_access(self):
        """Update access statistics."""
        self.last_accessed = time.time()
        self.access_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "ttl_seconds": self.ttl_seconds,
            "size_bytes": self.size_bytes,
            "tags": self.tags,
        }


class CacheStats:
    """Cache statistics tracking."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expired_entries = 0
        self.memory_usage_bytes = 0
        self.total_entries = 0
        self._lock = threading.RLock()

    def record_hit(self):
        """Record a cache hit."""
        with self._lock:
            self.hits += 1

    def record_miss(self):
        """Record a cache miss."""
        with self._lock:
            self.misses += 1

    def record_eviction(self):
        """Record a cache eviction."""
        with self._lock:
            self.evictions += 1

    def record_expiration(self):
        """Record an entry expiration."""
        with self._lock:
            self.expired_entries += 1

    def update_memory_usage(self, new_usage: int, entry_count: int):
        """Update memory usage statistics."""
        with self._lock:
            self.memory_usage_bytes = new_usage
            self.total_entries = entry_count

    def get_hit_ratio(self) -> float:
        """Get cache hit ratio."""
        with self._lock:
            total = self.hits + self.misses
            return self.hits / total if total > 0 else 0.0

    def get_stats_dict(self) -> Dict[str, Any]:
        """Get statistics as dictionary."""
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "expired_entries": self.expired_entries,
                "memory_usage_bytes": self.memory_usage_bytes,
                "total_entries": self.total_entries,
                "hit_ratio": self.get_hit_ratio(),
            }


class EvictionPolicy(ABC):
    """Abstract base class for cache eviction policies."""

    @abstractmethod
    def should_evict(self, entries: Dict[str, CacheEntry], max_size: int) -> List[str]:
        """Determine which entries to evict."""
        pass


class LRUEvictionPolicy(EvictionPolicy):
    """Least Recently Used eviction policy."""

    def should_evict(self, entries: Dict[str, CacheEntry], max_size: int) -> List[str]:
        if len(entries) <= max_size:
            return []

        # Sort by last accessed time
        sorted_entries = sorted(entries.values(), key=lambda e: e.last_accessed)

        # Return keys to evict
        to_evict = len(entries) - max_size
        return [entry.key for entry in sorted_entries[:to_evict]]


class LFUEvictionPolicy(EvictionPolicy):
    """Least Frequently Used eviction policy."""

    def should_evict(self, entries: Dict[str, CacheEntry], max_size: int) -> List[str]:
        if len(entries) <= max_size:
            return []

        # Sort by access count, then by last accessed time
        sorted_entries = sorted(
            entries.values(), key=lambda e: (e.access_count, e.last_accessed)
        )

        to_evict = len(entries) - max_size
        return [entry.key for entry in sorted_entries[:to_evict]]


class TTLEvictionPolicy(EvictionPolicy):
    """Time-to-Live based eviction policy."""

    def should_evict(self, entries: Dict[str, CacheEntry], max_size: int) -> List[str]:
        # First evict expired entries
        expired_keys = [key for key, entry in entries.items() if entry.is_expired()]

        # If we still need more space, use LRU for remaining
        if len(entries) - len(expired_keys) > max_size:
            remaining_entries = {
                k: v for k, v in entries.items() if k not in expired_keys
            }
            lru_evictions = LRUEvictionPolicy().should_evict(
                remaining_entries, max_size - len(expired_keys)
            )
            expired_keys.extend(lru_evictions)

        return expired_keys


class MemoryCache:
    """
    High-performance in-memory cache with TTL, LRU eviction, and statistics.
    """

    def __init__(
        self,
        max_size: int = 1000,
        max_memory_mb: int = 100,
        default_ttl_seconds: Optional[float] = None,
        eviction_policy: EvictionPolicy = None,
    ):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.default_ttl_seconds = default_ttl_seconds
        self.eviction_policy = eviction_policy or TTLEvictionPolicy()

        self._data: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self.stats = CacheStats()

        # Start cleanup thread
        self._cleanup_interval = 60  # seconds
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        with self._lock:
            entry = self._data.get(key)

            if entry is None:
                self.stats.record_miss()
                return None

            if entry.is_expired():
                del self._data[key]
                self.stats.record_expiration()
                self.stats.record_miss()
                return None

            entry.update_access()
            self.stats.record_hit()
            return entry.value

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        tags: List[str] = None,
    ) -> bool:
        """Put value in cache."""
        with self._lock:
            # Calculate size
            try:
                size_bytes = len(pickle.dumps(value))
            except Exception:
                size_bytes = len(str(value).encode("utf-8"))

            # Check if single entry would exceed memory limit
            if size_bytes > self.max_memory_bytes:
                return False

            # Create cache entry
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=1,
                ttl_seconds=ttl_seconds or self.default_ttl_seconds,
                size_bytes=size_bytes,
                tags=tags or [],
            )

            # Remove old entry if exists
            if key in self._data:
                del self._data[key]

            self._data[key] = entry

            # Enforce size and memory limits
            self._enforce_limits()

            self._update_memory_stats()
            return True

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._update_memory_stats()
                return True
            return False

    def clear(self):
        """Clear all entries from cache."""
        with self._lock:
            self._data.clear()
            self._update_memory_stats()

    def get_by_tags(self, tags: List[str]) -> Dict[str, Any]:
        """Get all entries that have any of the specified tags."""
        with self._lock:
            result = {}
            for key, entry in self._data.items():
                if not entry.is_expired() and any(tag in entry.tags for tag in tags):
                    entry.update_access()
                    result[key] = entry.value
            return result

    def delete_by_tags(self, tags: List[str]) -> int:
        """Delete all entries that have any of the specified tags."""
        with self._lock:
            to_delete = []
            for key, entry in self._data.items():
                if any(tag in entry.tags for tag in tags):
                    to_delete.append(key)

            for key in to_delete:
                del self._data[key]

            self._update_memory_stats()
            return len(to_delete)

    def _enforce_limits(self):
        """Enforce size and memory limits."""
        # Remove expired entries first
        expired_keys = [key for key, entry in self._data.items() if entry.is_expired()]
        for key in expired_keys:
            del self._data[key]
            self.stats.record_expiration()

        # Check if we still need to evict more entries
        current_memory = sum(entry.size_bytes for entry in self._data.values())

        if len(self._data) > self.max_size or current_memory > self.max_memory_bytes:
            # Use eviction policy to determine what to remove
            effective_max_size = min(
                self.max_size,
                len(self._data) * self.max_memory_bytes // max(current_memory, 1),
            )

            keys_to_evict = self.eviction_policy.should_evict(
                self._data, effective_max_size
            )

            for key in keys_to_evict:
                if key in self._data:
                    del self._data[key]
                    self.stats.record_eviction()

    def _update_memory_stats(self):
        """Update memory usage statistics."""
        total_memory = sum(entry.size_bytes for entry in self._data.values())
        self.stats.update_memory_usage(total_memory, len(self._data))

    def _cleanup_loop(self):
        """Background cleanup loop."""
        while True:
            try:
                time.sleep(self._cleanup_interval)
                with self._lock:
                    expired_keys = [
                        key for key, entry in self._data.items() if entry.is_expired()
                    ]
                    for key in expired_keys:
                        del self._data[key]
                        self.stats.record_expiration()

                    if expired_keys:
                        self._update_memory_stats()
            except Exception as e:
                # Log error if logger is available
                try:
                    from pt_logging_system import log_error

                    log_error(f"Cache cleanup error: {e}")
                except ImportError:
                    print(f"Cache cleanup error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            stats = self.stats.get_stats_dict()
            stats["max_size"] = self.max_size
            stats["max_memory_mb"] = self.max_memory_bytes // (1024 * 1024)
            stats["current_size"] = len(self._data)
            return stats

    def get_keys(self) -> List[str]:
        """Get all non-expired cache keys."""
        with self._lock:
            return [key for key, entry in self._data.items() if not entry.is_expired()]


class PersistentCache:
    """
    Persistent cache that stores data on disk with memory backing.
    """

    def __init__(self, cache_dir: str, memory_cache: MemoryCache = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.memory_cache = memory_cache or MemoryCache(max_size=100, max_memory_mb=50)
        self._lock = threading.RLock()

    def _get_file_path(self, key: str) -> Path:
        """Get file path for cache key."""
        # Hash the key to create a valid filename
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache (memory first, then disk)."""
        with self._lock:
            # Try memory cache first
            value = self.memory_cache.get(key)
            if value is not None:
                return value

            # Try disk cache
            file_path = self._get_file_path(key)
            if file_path.exists():
                try:
                    with open(file_path, "rb") as f:
                        entry_data = pickle.load(f)

                    entry = CacheEntry(**entry_data["metadata"])

                    if not entry.is_expired():
                        value = entry_data["value"]
                        # Put back in memory cache
                        self.memory_cache.put(key, value, entry.ttl_seconds, entry.tags)
                        return value
                    else:
                        # Remove expired file
                        file_path.unlink()

                except Exception as e:
                    # Log error and remove corrupted file
                    try:
                        from pt_logging_system import log_error

                        log_error(f"Error reading cache file {file_path}: {e}")
                    except ImportError:
                        print(f"Error reading cache file {file_path}: {e}")

                    if file_path.exists():
                        file_path.unlink()

            return None

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        tags: List[str] = None,
    ) -> bool:
        """Put value in cache (both memory and disk)."""
        with self._lock:
            # Put in memory cache
            self.memory_cache.put(key, value, ttl_seconds, tags)

            # Save to disk
            try:
                entry = CacheEntry(
                    key=key,
                    value=None,  # Don't store value in metadata
                    created_at=time.time(),
                    last_accessed=time.time(),
                    access_count=1,
                    ttl_seconds=ttl_seconds,
                    tags=tags or [],
                )

                entry_data = {"metadata": entry.to_dict(), "value": value}

                file_path = self._get_file_path(key)
                with open(file_path, "wb") as f:
                    pickle.dump(entry_data, f)

                return True

            except Exception as e:
                try:
                    from pt_logging_system import log_error

                    log_error(f"Error writing cache file for key {key}: {e}")
                except ImportError:
                    print(f"Error writing cache file for key {key}: {e}")
                return False

    def delete(self, key: str) -> bool:
        """Delete value from cache (both memory and disk)."""
        with self._lock:
            # Remove from memory
            self.memory_cache.delete(key)

            # Remove from disk
            file_path = self._get_file_path(key)
            if file_path.exists():
                try:
                    file_path.unlink()
                    return True
                except Exception as e:
                    try:
                        from pt_logging_system import log_error

                        log_error(f"Error deleting cache file {file_path}: {e}")
                    except ImportError:
                        print(f"Error deleting cache file {file_path}: {e}")

            return False

    def clear(self):
        """Clear all cache data."""
        with self._lock:
            self.memory_cache.clear()

            # Remove all cache files
            for file_path in self.cache_dir.glob("*.cache"):
                try:
                    file_path.unlink()
                except Exception:
                    pass

    def cleanup_expired(self) -> int:
        """Clean up expired cache files."""
        with self._lock:
            removed_count = 0

            for file_path in self.cache_dir.glob("*.cache"):
                try:
                    with open(file_path, "rb") as f:
                        entry_data = pickle.load(f)

                    entry = CacheEntry(**entry_data["metadata"])

                    if entry.is_expired():
                        file_path.unlink()
                        removed_count += 1

                except Exception:
                    # Remove corrupted files
                    file_path.unlink()
                    removed_count += 1

            return removed_count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        memory_stats = self.memory_cache.get_stats()

        # Count disk files
        disk_files = len(list(self.cache_dir.glob("*.cache")))

        # Calculate disk usage
        disk_usage = sum(f.stat().st_size for f in self.cache_dir.glob("*.cache"))

        return {
            **memory_stats,
            "disk_files": disk_files,
            "disk_usage_bytes": disk_usage,
            "disk_usage_mb": disk_usage / (1024 * 1024),
        }


class CacheManager:
    """
    Main cache manager that provides different cache backends and strategies.
    """

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            import pt_paths

            cache_dir = pt_paths.cache_dir()
        self.cache_dir = cache_dir

        # Initialize different cache types
        self.memory_cache = MemoryCache(max_size=1000, max_memory_mb=100)
        self.persistent_cache = PersistentCache(self.cache_dir, self.memory_cache)

        # Specialized caches
        self.market_data_cache = MemoryCache(
            max_size=500, max_memory_mb=50, default_ttl_seconds=60
        )
        self.model_cache = PersistentCache(os.path.join(self.cache_dir, "models"))
        self.config_cache = MemoryCache(
            max_size=100, max_memory_mb=10, default_ttl_seconds=300
        )

    def get_market_data(self, key: str) -> Optional[Any]:
        """Get market data from specialized cache."""
        return self.market_data_cache.get(key)

    def cache_market_data(self, key: str, data: Any, ttl_seconds: int = 60) -> bool:
        """Cache market data with short TTL."""
        return self.market_data_cache.put(key, data, ttl_seconds, ["market_data"])

    def get_model(self, model_id: str) -> Optional[Any]:
        """Get cached model."""
        return self.model_cache.get(model_id)

    def cache_model(
        self, model_id: str, model_data: Any, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Cache model data persistently."""
        return self.model_cache.put(model_id, model_data, ttl_seconds, ["model"])

    def get_config(self, config_key: str) -> Optional[Any]:
        """Get cached configuration."""
        return self.config_cache.get(config_key)

    def cache_config(
        self, config_key: str, config_data: Any, ttl_seconds: int = 300
    ) -> bool:
        """Cache configuration data."""
        return self.config_cache.put(config_key, config_data, ttl_seconds, ["config"])

    def clear_all_caches(self):
        """Clear all caches."""
        self.memory_cache.clear()
        self.persistent_cache.clear()
        self.market_data_cache.clear()
        self.model_cache.clear()
        self.config_cache.clear()

    def cleanup_expired(self) -> Dict[str, int]:
        """Clean up expired entries from all caches."""
        return {
            "persistent_cache": self.persistent_cache.cleanup_expired(),
            "model_cache": self.model_cache.cleanup_expired(),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics from all caches."""
        return {
            "memory_cache": self.memory_cache.get_stats(),
            "persistent_cache": self.persistent_cache.get_stats(),
            "market_data_cache": self.market_data_cache.get_stats(),
            "model_cache": self.model_cache.get_stats(),
            "config_cache": self.config_cache.get_stats(),
        }


def cached(
    cache_manager: CacheManager,
    ttl_seconds: Optional[int] = None,
    tags: List[str] = None,
    cache_type: str = "memory",
):
    """
    Decorator for caching function results.

    Args:
        cache_manager: Cache manager instance
        ttl_seconds: Time to live in seconds
        tags: Cache tags
        cache_type: Type of cache ('memory' or 'persistent')
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key_data = {
                "func": func.__name__,
                "args": args,
                "kwargs": sorted(kwargs.items()),
            }
            key = hashlib.md5(str(key_data).encode()).hexdigest()

            # Try to get from cache
            cache = (
                cache_manager.persistent_cache
                if cache_type == "persistent"
                else cache_manager.memory_cache
            )
            result = cache.get(key)

            if result is not None:
                return result

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.put(key, result, ttl_seconds, tags)

            return result

        return wrapper

    return decorator


# Global cache manager instance
_global_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager


def setup_cache_manager(cache_dir: str = None) -> CacheManager:
    """Setup and return the global cache manager."""
    global _global_cache_manager
    _global_cache_manager = CacheManager(cache_dir)
    return _global_cache_manager


if __name__ == "__main__":
    # Example usage and testing
    cache_manager = CacheManager("test_cache")

    # Test memory cache
    cache_manager.memory_cache.put("test_key", {"data": "test_value"}, ttl_seconds=60)
    print("Memory cache get:", cache_manager.memory_cache.get("test_key"))

    # Test market data cache
    cache_manager.cache_market_data(
        "BTCUSDT", {"price": 50000, "volume": 1000}, ttl_seconds=30
    )
    print("Market data:", cache_manager.get_market_data("BTCUSDT"))

    # Test model cache
    cache_manager.cache_model("btc_model_v1", {"weights": [1, 2, 3, 4, 5]})
    print("Model data:", cache_manager.get_model("btc_model_v1"))

    # Test decorator
    @cached(cache_manager, ttl_seconds=300, tags=["test"])
    def expensive_operation(x, y):
        print(f"Computing expensive operation for {x}, {y}")
        time.sleep(1)  # Simulate expensive operation
        return x * y + 100

    print("First call:", expensive_operation(5, 10))
    print("Cached call:", expensive_operation(5, 10))  # Should be instant

    # Display stats
    stats = cache_manager.get_all_stats()
    print("\nCache Statistics:")
    for cache_name, cache_stats in stats.items():
        print(f"{cache_name}: {cache_stats}")

    print("\nCache testing completed!")
