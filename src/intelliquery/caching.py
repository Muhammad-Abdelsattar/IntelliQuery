import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class CacheProvider(Protocol):
    """
    A protocol defining the interface for a key-value cache.
    This allows for interchangeable caching strategies (in-memory, file, Redis, etc.).
    """

    def get(self, key: str) -> Optional[str]:
        """Retrieves a value from the cache. Returns None on a cache miss."""
        ...

    def set(self, key: str, value: str) -> None:
        """Saves a value to the cache."""
        ...


class InMemoryCacheProvider:
    """A simple, non-persistent cache that stores data in a dictionary."""

    def __init__(self):
        self._cache: dict[str, str] = {}
        logger.info("Initialized InMemoryCacheProvider.")

    def get(self, key: str) -> Optional[str]:
        return self._cache.get(key)

    def set(self, key: str, value: str) -> None:
        self._cache[key] = value


class FileSystemCacheProvider:
    """
    A persistent cache that stores data as files on the local filesystem.
    Keys are hashed to create safe filenames.
    """

    def __init__(self, cache_dir: Path = Path("cache/context_cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Initialized FileSystemCacheProvider at '{self.cache_dir.resolve()}'."
        )

    def _key_to_path(self, key: str) -> Path:
        """Hashes the key to create a stable and safe filename."""
        hashed_key = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed_key}.json"

    def get(self, key: str) -> Optional[str]:
        cache_path = self._key_to_path(key)
        if not cache_path.is_file():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)["content"]
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error(f"Failed to read from cache file {cache_path}: {e}")
            return None

    def set(self, key: str, value: str) -> None:
        cache_path = self._key_to_path(key)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"content": value}, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to write to cache file {cache_path}: {e}")
