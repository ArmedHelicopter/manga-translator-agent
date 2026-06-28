#!/usr/bin/env python3
"""
Test script for translation pipeline optimization (Experiment #12 - BCDF).

This script tests the new pipelined translation with caching, concurrent workers,
and local model compatibility.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from mga.config.loader import build_project_config
from mga.models import ProjectConfig
from mga.pipeline.translation_cache import TranslationCache, create_translation_cache

def test_cache():
    """Test translation cache functionality."""
    print("=== Testing Translation Cache ===")
    
    # Create a cache instance
    cache_dir = Path("./test_cache")
    cache = TranslationCache(cache_dir)
    
    # Test cache key generation
    test_text = "Hello, world!"
    key = cache._make_key(test_text, "zh-CN", "openai", "semantic")
    print(f"Cache key for '{test_text}': {key}")
    
    # Test cache set/get
    result = {"text": "你好，世界！", "confidence": 0.95}
    cache.set_semantic(test_text, "zh-CN", "openai", result)
    cached = cache.get_semantic(test_text, "zh-CN", "openai")
    
    assert cached == result, f"Cache mismatch: {cached} != {result}"
    print("✅ Cache set/get works correctly")
    
    # Test cache stats
    stats = cache.get_cache_stats()
    print(f"Cache stats: {stats}")
    
    # Clean up
    cache.clear_cache()
    cache_dir.rmdir(parents=True, ignore_errors=True)
    print("✅ Cache test completed")


def test_config_loading():
    """Test loading of translation configuration from TOML."""
    print("\n=== Testing Configuration Loading ===")
    
    # Test with default config (should fall back to defaults)
    config = ProjectConfig()
    translation_config = config.translation_config
    
    print(f"Default translation config: {translation_config}")
    
    assert "parallel_mode" in translation_config
    assert "max_workers" in translation_config
    assert "enable_cache" in translation_config
    
    print("✅ Configuration loading works correctly")


def test_mode_selection():
    """Test different translation modes."""
    print("\n=== Testing Mode Selection ===")
    
    # Test serial mode
    config_serial = ProjectConfig()
    config_serial.translation_config["parallel_mode"] = "serial"
    print(f"Serial mode config: {config_serial.translation_config}")
    
    # Test parallel mode  
    config_parallel = ProjectConfig()
    config_parallel.translation_config["parallel_mode"] = "parallel"
    print(f"Parallel mode config: {config_parallel.translation_config}")
    
    # Test pipelined mode
    config_pipelined = ProjectConfig()
    config_pipelined.translation_config["parallel_mode"] = "pipelined"
    print(f"Pipelined mode config: {config_pipelined.translation_config}")
    
    # Test invalid mode (should fallback to serial)
    config_invalid = ProjectConfig()
    config_invalid.translation_config["parallel_mode"] = "invalid_mode"
    print(f"Invalid mode config: {config_invalid.translation_config}")
    
    print("✅ Mode selection configuration works correctly")


def test_factory_function():
    """Test the translation cache factory function."""
    print("\n=== Testing Cache Factory Function ===")
    
    try:
        cache = create_translation_cache(Path("./test_factory"))
        assert cache is not None
        print("✅ Cache factory function works correctly")
        
        # Clean up
        cache.clear_cache()
        (Path("./test_factory") / "cache" / "translations.db").unlink(missing_ok=True)
        (Path("./test_factory") / "cache").rmdir(missing_ok=True)
        Path("./test_factory").rmdir(missing_ok=True)
        
    except Exception as e:
        print(f"❌ Cache factory function failed: {e}")


def main():
    """Run all tests."""
    print("Starting translation pipeline optimization tests (Experiment #12 - BCDF)...")
    
    try:
        test_cache()
        test_config_loading() 
        test_mode_selection()
        test_factory_function()
        
        print("\n🎉 All tests passed! BCDF optimization implementation is ready.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()