import json
from pathlib import Path

from intelliquery.core.caching import InMemoryCacheProvider, FileSystemCacheProvider


def test_in_memory_cache_set_and_get():
    """Verify that we can set a value and get it back."""
    cache = InMemoryCacheProvider()
    cache.set("my-key", "my-value")
    assert cache.get("my-key") == "my-value"

def test_in_memory_cache_miss():
    """Verify that getting a non-existent key returns None."""
    cache = InMemoryCacheProvider()
    assert cache.get("non-existent-key") is None


def test_file_system_cache_set_and_get(tmp_path: Path):
    """
    Verify FileSystemCacheProvider creates a file and can read from it.
    Uses pytest's tmp_path fixture to create a temporary directory.
    """
    cache = FileSystemCacheProvider(cache_dir=tmp_path)
    key = "my-file-key"
    value = '{"data": "some content"}'
    
    cache.set(key, value)
    
    # Check that the file was created and contains the correct data
    expected_path = cache._key_to_path(key)
    assert expected_path.exists()
    with open(expected_path, "r") as f:
        content = json.load(f)
        assert content["content"] == value
        
    # Check that get retrieves the value correctly
    assert cache.get(key) == value

def test_file_system_cache_miss(tmp_path: Path):
    """Verify it returns None for a key that doesn't have a corresponding file."""
    cache = FileSystemCacheProvider(cache_dir=tmp_path)
    assert cache.get("non-existent-key") is None

def test_file_system_cache_handles_bad_json(tmp_path: Path):
    """Verify that if a cache file is corrupted, it returns None instead of crashing."""
    cache = FileSystemCacheProvider(cache_dir=tmp_path)
    key = "corrupted-key"
    
    # Manually create a corrupted file
    cache_path = cache._key_to_path(key)
    with open(cache_path, "w") as f:
        f.write("this is not valid json")
        
    # The get method should handle the error gracefully
    assert cache.get(key) is None
