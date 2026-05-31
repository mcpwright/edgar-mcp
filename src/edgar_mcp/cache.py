"""A tiny async in-memory cache: TTL expiry + byte-budgeted LRU eviction.

Used to avoid re-fetching SEC responses — most importantly the ~1.6 MB ticker
map that name resolution hits constantly, and immutable filing-archive content.
Bounded by total cached bytes so it can't grow without limit.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """In-memory cache keyed by string, with per-entry TTL and a byte budget.

    Entries are evicted oldest-first (LRU) once the total tracked size exceeds
    ``max_bytes``. Thread-safe across asyncio tasks via an internal lock.
    """

    def __init__(self, max_bytes: int = 64_000_000) -> None:
        # key -> (expires_at_monotonic, size_bytes, value)
        self._store: OrderedDict[str, tuple[float, int, Any]] = OrderedDict()
        self._max_bytes = max_bytes
        self._cur_bytes = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> tuple[bool, Any]:
        """Return ``(hit, value)``; a miss (absent or expired) is ``(False, None)``."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            expires_at, _size, value = entry
            if expires_at < time.monotonic():
                self._evict(key)
                return False, None
            self._store.move_to_end(key)  # mark most-recently-used
            return True, value

    async def set(self, key: str, value: Any, ttl: float, size: int = 0) -> None:
        """Cache ``value`` under ``key`` for ``ttl`` seconds; ``size`` is its
        approximate byte cost for the eviction budget."""
        async with self._lock:
            if key in self._store:
                self._evict(key)
            self._store[key] = (time.monotonic() + ttl, size, value)
            self._cur_bytes += size
            self._store.move_to_end(key)
            while self._cur_bytes > self._max_bytes and len(self._store) > 1:
                oldest = next(iter(self._store))
                self._evict(oldest)

    def _evict(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry is not None:
            self._cur_bytes -= entry[1]
