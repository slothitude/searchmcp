"""aiosqlite-backed cache with count-based LRU eviction and stampede protection."""

import asyncio
import json
import logging
import os
import time

import aiosqlite

from config import CACHE_DIR, CACHE_CONFIG

logger = logging.getLogger(__name__)

# Schema column indices (SELECT *)
IDX_KEY = 0
IDX_URL = 1
IDX_CONTENT_TYPE = 2
IDX_CONTENT = 3
IDX_METADATA = 4
IDX_CREATED = 5
IDX_LAST_ACCESSED = 6
IDX_EXPIRES = 7
IDX_HIT_COUNT = 8

_db: aiosqlite.Connection | None = None
_locks: dict[str, asyncio.Lock] = {}


async def init() -> None:
    """Open (or create) the cache database. Call once at startup."""
    global _db
    os.makedirs(CACHE_DIR, exist_ok=True)
    db_path = os.path.join(CACHE_DIR, "cache.db")
    _db = await aiosqlite.connect(db_path)
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute(
        """CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            content_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at REAL NOT NULL,
            last_accessed REAL NOT NULL,
            expires_at REAL NOT NULL,
            hit_count INTEGER DEFAULT 0
        )"""
    )
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)"
    )
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_cache_type ON cache(content_type)"
    )
    await _db.commit()
    await _evict_expired()


async def close() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


def _get_lock(key: str) -> asyncio.Lock:
    """Per-key lock for stampede protection (in-process only)."""
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


async def _fetchone(query: str, params=()):
    """Execute a query and return the first row (tuple)."""
    cursor = await _db.execute(query, params)
    row = await cursor.fetchone()
    await cursor.close()
    return row


async def get(key: str) -> dict | None:
    """Return cached entry if it exists and hasn't expired, else None."""
    if not _db:
        return None
    now = time.time()
    # Update hit count and last_accessed first
    cursor = await _db.execute(
        "UPDATE cache SET last_accessed = ?, hit_count = hit_count + 1 WHERE key = ? AND expires_at > ?",
        (now, key, now),
    )
    updated = cursor.rowcount
    await cursor.close()
    await _db.commit()
    if not updated:
        return None
    row = await _fetchone(
        "SELECT * FROM cache WHERE key = ?",
        (key,),
    )
    if row:
        meta = None
        if row[IDX_METADATA]:
            meta = json.loads(row[IDX_METADATA])
        return {
            "content": row[IDX_CONTENT],
            "metadata": meta,
            "content_type": row[IDX_CONTENT_TYPE],
            "hit_count": row[IDX_HIT_COUNT],
        }
    return None


async def put(key: str, url: str, content: str, content_type: str,
             metadata: dict | None = None) -> None:
    """Store an entry in the cache, evicting if over limit."""
    if not _db:
        return
    now = time.time()
    cfg = CACHE_CONFIG.get(content_type, CACHE_CONFIG["extracted"])
    expires = now + cfg["ttl"]

    meta_json = json.dumps(metadata) if metadata else None

    await _db.execute(
        """INSERT OR REPLACE INTO cache (key, url, content_type, content, metadata,
           created_at, last_accessed, expires_at, hit_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (key, url, content_type, content, meta_json, now, now, expires),
    )
    await _db.commit()
    await _evict_type(content_type)


async def clear(key: str | None = None) -> int:
    """Clear a specific key or all entries. Returns number of rows deleted."""
    if not _db:
        return 0
    if key:
        cursor = await _db.execute("DELETE FROM cache WHERE key = ?", (key,))
    else:
        cursor = await _db.execute("DELETE FROM cache")
    count = cursor.rowcount
    await cursor.close()
    await _db.commit()
    return count


async def stats() -> dict:
    """Return cache statistics."""
    if not _db:
        return {"error": "cache not initialized"}
    result = {}
    for ctype, cfg in CACHE_CONFIG.items():
        row = await _fetchone(
            "SELECT COUNT(*) FROM cache WHERE content_type = ?",
            (ctype,),
        )
        result[ctype] = {"count": row[0] if row else 0, "max": cfg["max_entries"], "ttl": cfg["ttl"]}
    row = await _fetchone("SELECT COUNT(*) FROM cache")
    result["total"] = row[0] if row else 0
    return result


async def _evict_type(content_type: str) -> None:
    """Evict oldest 10% by last_accessed if count exceeds max_entries."""
    if not _db:
        return
    cfg = CACHE_CONFIG.get(content_type)
    if not cfg:
        return
    row = await _fetchone(
        "SELECT COUNT(*) FROM cache WHERE content_type = ?",
        (content_type,),
    )
    count = row[0] if row else 0
    if count <= cfg["max_entries"]:
        return
    to_delete = max(1, int(cfg["max_entries"] * 0.1))
    await _db.execute(
        f"""DELETE FROM cache WHERE key IN (
            SELECT key FROM cache WHERE content_type = ?
            ORDER BY last_accessed ASC LIMIT {to_delete}
        )""",
        (content_type,),
    )
    await _db.commit()


async def _evict_expired() -> None:
    """Remove all expired entries."""
    if not _db:
        return
    now = time.time()
    await _db.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
    await _db.commit()
