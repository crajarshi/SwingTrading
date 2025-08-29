"""Data caching layer with SQLite for API efficiency."""

import sqlite3
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os

class DataCache:
    """SQLite cache with 24hr TTL for historical data.
    
    Key structure: {symbol}:{date}:{bars}
    Target: ≥90% hit rate on second run
    """
    
    def __init__(self, cache_file: str = "scoring_cache.db"):
        self.cache_file = cache_file
        self.ttl_seconds = 24 * 60 * 60  # 24 hours
        self.hits = 0
        self.misses = 0
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database with cache table."""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON cache(timestamp)
        """)
        conn.commit()
        conn.close()
    
    def get(self, symbol: str, date: str, bars: int) -> Optional[list]:
        """Retrieve cached data if valid."""
        cache_key = f"{symbol}:{date}:{bars}"
        
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data, timestamp FROM cache WHERE cache_key = ?",
            (cache_key,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            data, timestamp = result
            if time.time() - timestamp < self.ttl_seconds:
                self.hits += 1
                return json.loads(data)
            else:
                self._delete_expired(cache_key)
        
        self.misses += 1
        return None
    
    def set(self, symbol: str, date: str, bars: int, data: list):
        """Store data in cache."""
        cache_key = f"{symbol}:{date}:{bars}"
        
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO cache (cache_key, data, timestamp) VALUES (?, ?, ?)",
            (cache_key, json.dumps(data), time.time())
        )
        conn.commit()
        conn.close()
    
    def _delete_expired(self, cache_key: str):
        """Remove expired entry."""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache WHERE cache_key = ?", (cache_key,))
        conn.commit()
        conn.close()
    
    def clear_expired(self):
        """Remove all expired entries."""
        cutoff = time.time() - self.ttl_seconds
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    
    def get_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.get_hit_rate(),
            "total_requests": self.hits + self.misses
        }
    
    def reset_stats(self):
        """Reset hit/miss counters."""
        self.hits = 0
        self.misses = 0