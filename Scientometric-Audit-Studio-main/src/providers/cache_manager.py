"""
SQLite-backed persistent cache for external API responses.
Thread-safe, avoids duplicate network requests, and persists across restarts.
"""
import sqlite3
import json
import hashlib
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from config import BASE_DIR

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages local SQLite key-value cache for API responses.
    """
    _instance: Optional["CacheManager"] = None

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (BASE_DIR / "cache" / "api_cache.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def get_instance(cls) -> "CacheManager":
        if cls._instance is None:
            cls._instance = CacheManager()
        return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    namespace TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    status_code INTEGER,
                    response_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (namespace, cache_key)
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_ns_key 
                ON cache_entries (namespace, cache_key);
            """)

    @staticmethod
    def hash_key(key_raw: str) -> str:
        """Returns SHA-256 hash for raw string key."""
        return hashlib.sha256(key_raw.strip().lower().encode("utf-8")).hexdigest()

    def get(self, namespace: str, key_raw: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached response dict, or None if miss.
        """
        k_hash = self.hash_key(key_raw)
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT response_data, status_code FROM cache_entries WHERE namespace = ? AND cache_key = ?",
                    (namespace, k_hash),
                )
                row = cur.fetchone()
                if row and row[0]:
                    try:
                        return json.loads(row[0])
                    except json.JSONDecodeError:
                        return None
        except sqlite3.Error as e:
            logger.warning(f"Cache read error for [{namespace}]: {e}")
        return None

    def set(self, namespace: str, key_raw: str, data: Dict[str, Any], status_code: int = 200) -> None:
        """
        Persists response dict in cache.
        """
        k_hash = self.hash_key(key_raw)
        serialized = json.dumps(data, ensure_ascii=False)
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries (namespace, cache_key, status_code, response_data)
                    VALUES (?, ?, ?, ?)
                    """,
                    (namespace, k_hash, status_code, serialized),
                )
        except sqlite3.Error as e:
            logger.warning(f"Cache write error for [{namespace}]: {e}")

