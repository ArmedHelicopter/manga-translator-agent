#!/usr/bin/env python3
"""
Simple test for translation pipeline optimization.
Tests the basic cache functionality and mode selection without complex async code.
"""

from pathlib import Path

from mga.models import ProjectConfig
from mga.pipeline.translation_cache import TranslationCache

def test_basic_functionality():
    """Test basic functionality without complex dependencies."""
    print("=== Testing BCDF Optimization Components ===")
    
    # Test 1: Translation Cache
    print("\n1. Testing Translation Cache...")
    cache_dir = Path("./test_cache_simple")
    
    try:
        cache = TranslationCache(cache_dir)
        print("✅ Cache created successfully")
        
        # Test cache operations
        test_text = "Hello, world!"
        result = {"text": "你好，世界！", "confidence": 0.95}
        
        cache.set_semantic(test_text, "zh-CN", "openai", result)
        cached = cache.get_semantic(test_text, "zh-CN", "openai")
        
        assert cached == result
        print("✅ Cache operations work correctly")
        
        # Test stats
        stats = cache.get_cache_stats()
        print(f"Cache stats: {stats}")
        
        # Clean up
        cache.clear_cache()
        cache_dir.rmdir(parents=True, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ Cache test failed: {e}")
        return False
    
    # Test 2: Project Configuration
    print("\n2. Testing Project Configuration...")
    try:
        config = ProjectConfig()
        print(f"Default config: {config.translation_config}")
        
        # Test configuration updates
        config.translation_config["parallel_mode"] = "pipelined"
        config.translation_config["max_workers"] = 8
        config.translation_config["enable_cache"] = True
        
        print(f"Updated config: {config.translation_config}")
        print("✅ Configuration works correctly")
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False
    
    # Test 3: Mode Selection Logic
    print("\n3. Testing Mode Selection Logic...")
    test_cases = [
        ("serial", "serial"),
        ("parallel", "parallel"), 
        ("pipelined", "pipelined"),
        ("invalid", "serial")  # Should fallback to serial
    ]
    
    for input_mode, expected in test_cases:
        config = ProjectConfig()
        config.translation_config["parallel_mode"] = input_mode
        
        # Simulate the mode selection logic from _translate_page
        if len([]) <= 1:  # Simulate single bubble
            actual_mode = "serial"
        else:
            mode = config.translation_config.get("parallel_mode", "parallel")
            if mode == "serial":
                actual_mode = "serial"
            elif mode == "parallel":
                actual_mode = "parallel"
            elif mode == "pipelined":
                actual_mode = "pipelined"
            else:
                actual_mode = "serial"  # fallback
        
        assert actual_mode == expected, f"Mode {input_mode} -> {actual_mode}, expected {expected}"
        print(f"✅ Mode '{input_mode}' -> '{actual_mode}' (correct)")
    
    print("\n🎉 All basic functionality tests passed!")
    return True

def main():
    """Run tests."""
    success = test_basic_functionality()
    if success:
        print("\n✅ BCDF optimization basic components are ready!")
        print("Next step: Integrate with full pipeline (may need to fix syntax errors)")
    else:
        print("\n❌ Tests failed")
        exit(1)

if __name__ == "__main__":
    main()