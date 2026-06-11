"""
Translation caching system for performance optimization.
Provides persistent SQLite-based caching for semantic and translation results.
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, Any


class TranslationCache:
    """
    SQLite-based translation cache with automatic TTL expiration.
    
    Cache keys are deterministic based on:
    - source text content
    - target language
    - provider name
    - cache stage (semantic/persona) — encoded in key hash only, not a DB column
    """
    
    def __init__(self, working_dir: Path):
        """
        Initialize cache with working directory path.
        
        Args:
            working_dir: Base directory for cache storage
        """
        self.cache_dir = working_dir / "cache" / "translations"
        self.db_path = self.cache_dir / "translations.db"
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database with proper schema (no stage column)."""
        conn = sqlite3.connect(self.db_path)
        
        # Create table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                key TEXT PRIMARY KEY,
                semantic_json TEXT,
                persona_json TEXT,
                timestamp INTEGER,
                target_lang TEXT,
                provider_name TEXT,
                source_text_hash TEXT
            )
        """)
        
        # Create indexes for faster lookups
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON translations(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_target_lang ON translations(target_lang)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_provider_name ON translations(provider_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_hash ON translations(source_text_hash)")
        
        conn.commit()
        conn.close()
    
    def _make_key(self, source_text: str, target_lang: str, provider_name: str, stage: str) -> str:
        """
        Generate deterministic cache key.
        
        Args:
            source_text: Original bubble text
            target_lang: Target language code
            provider_name: LLM provider name
            stage: "semantic" or "persona" — embedded in hash, not a DB column
            
        Returns:
            SHA256 hash key
        """
        # Use normalized text to avoid cache misses from whitespace differences
        normalized_text = source_text.strip()
        payload = f"{normalized_text}|{target_lang}|{provider_name}|{stage}"
        return hashlib.sha256(payload.encode()).hexdigest()
    
    def _clean_expired_cache(self, ttl_days: int = 30):
        """Remove expired cache entries."""
        if ttl_days <= 0:
            return
            
        cutoff_time = int(time.time()) - (ttl_days * 24 * 60 * 60)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM translations WHERE timestamp < ?", (cutoff_time,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted_count
    
    def get_semantic(self, source_text: str, target_lang: str, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        Get cached semantic translation result.
        
        Args:
            source_text: Original bubble text
            target_lang: Target language code
            provider_name: LLM provider name
            
        Returns:
            Cached semantic result or None if not found/expired
        """
        key = self._make_key(source_text, target_lang, provider_name, "semantic")
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute("""
            SELECT semantic_json, timestamp 
            FROM translations 
            WHERE key = ?
            ORDER BY timestamp DESC LIMIT 1
        """, (key,)).fetchone()
        
        conn.close()
        
        if row and row['semantic_json']:
            return json.loads(row['semantic_json'])
        return None
    
    def set_semantic(self, source_text: str, target_lang: str, provider_name: str, result: Dict[str, Any]):
        """
        Cache semantic translation result.
        
        Args:
            source_text: Original bubble text
            target_lang: Target language code
            provider_name: LLM provider name
            result: Semantic translation result dict
        """
        key = self._make_key(source_text, target_lang, provider_name, "semantic")
        source_hash = hashlib.sha256(source_text.strip().encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO translations 
            (key, semantic_json, timestamp, target_lang, provider_name, source_text_hash)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, json.dumps(result), int(time.time()), target_lang, provider_name, source_hash))
        conn.commit()
        conn.close()
    
    def get_persona(self, source_text: str, target_lang: str, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        Get cached persona translation result.
        
        Args:
            source_text: Original bubble text
            target_lang: Target language code
            provider_name: LLM provider name
            
        Returns:
            Cached persona result or None if not found/expired
        """
        key = self._make_key(source_text, target_lang, provider_name, "persona")
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute("""
            SELECT persona_json, timestamp 
            FROM translations 
            WHERE key = ?
            ORDER BY timestamp DESC LIMIT 1
        """, (key,)).fetchone()
        
        conn.close()
        
        if row and row['persona_json']:
            return json.loads(row['persona_json'])
        return None
    
    def set_persona(self, source_text: str, target_lang: str, provider_name: str, result: Dict[str, Any]):
        """
        Cache persona translation result.
        
        Args:
            source_text: Original bubble text
            target_lang: Target language code
            provider_name: LLM provider name
            result: Persona translation result dict
        """
        key = self._make_key(source_text, target_lang, provider_name, "persona")
        source_hash = hashlib.sha256(source_text.strip().encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO translations 
            (key, persona_json, timestamp, target_lang, provider_name, source_text_hash)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, json.dumps(result), int(time.time()), target_lang, provider_name, source_hash))
        conn.commit()
        conn.close()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # Total entries
        total = conn.execute("SELECT COUNT(*) as count FROM translations").fetchone()
        
        # Entries by semantic vs persona (inferred from which column is non-null)
        semantic = conn.execute("SELECT COUNT(*) as count FROM translations WHERE semantic_json IS NOT NULL").fetchone()
        persona = conn.execute("SELECT COUNT(*) as count FROM translations WHERE persona_json IS NOT NULL").fetchone()
        
        # Entries by provider
        providers = conn.execute("""
            SELECT provider_name, COUNT(*) as count 
            FROM translations 
            GROUP BY provider_name
        """).fetchall()
        
        # Oldest and newest entries
        oldest = conn.execute("SELECT MIN(timestamp) as timestamp FROM translations").fetchone()
        newest = conn.execute("SELECT MAX(timestamp) as timestamp FROM translations").fetchone()
        
        conn.close()
        
        return {
            "total_entries": total["count"],
            "semantic_entries": semantic["count"],
            "persona_entries": persona["count"],
            "providers": {p["provider_name"]: p["count"] for p in providers},
            "oldest_entry": oldest["timestamp"] if oldest["timestamp"] else None,
            "newest_entry": newest["timestamp"] if newest["timestamp"] else None,
            "cache_dir": str(self.cache_dir),
            "database_path": str(self.db_path)
        }
    
    def clear_cache(self):
        """Clear all cache entries."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM translations")
        conn.commit()
        conn.close()


# Factory function for cache initialization
def create_translation_cache(working_dir: Path) -> TranslationCache:
    """
    Factory function to create TranslationCache with config-based cleanup.
    
    Args:
        working_dir: Working directory for cache storage
        
    Returns:
        Initialized TranslationCache instance
    """
    cache = TranslationCache(working_dir)
    
    # Clean expired entries based on default config
    cache_config = 30  # Default TTL
    try:
        deleted_count = cache._clean_expired_cache(cache_config)
        if deleted_count and deleted_count > 0:
            print(f"[cache] Cleaned up {deleted_count} expired cache entries")
    except Exception:
        # Silently ignore errors - cache still works
        pass
    
    return cache
