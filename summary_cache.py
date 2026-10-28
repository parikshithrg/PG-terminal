"""Small evidence-aware cache for expensive local read models."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Hashable, TypeVar


T = TypeVar("T")


def local_evidence_fingerprint(
    database_path: str | Path,
    *,
    business_date: str,
    extra: Hashable | None = None,
) -> tuple[object, ...]:
    """Return a cheap identity that changes when SQLite or its WAL changes."""
    database = Path(database_path)
    files: list[tuple[str, int, int]] = []
    for candidate in (
        database,
        Path(f"{database}-wal"),
    ):
        try:
            stat = candidate.stat()
            files.append((candidate.name, stat.st_size, stat.st_mtime_ns))
        except FileNotFoundError:
            files.append((candidate.name, -1, -1))
    return (business_date, tuple(files), extra)


class EvidenceResponseCache:
    """Thread-safe LRU cache keyed by an explicit evidence fingerprint."""

    def __init__(self, max_entries: int = 16):
        if max_entries < 1:
            raise ValueError("max_entries_must_be_positive")
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[Hashable, object]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._total_build_ms = 0.0

    def get_or_build(
        self,
        key: str,
        fingerprint: Hashable,
        builder: Callable[[], T],
    ) -> tuple[T, str, float]:
        """Return payload, hit/miss state and request-side elapsed milliseconds."""
        started = time.perf_counter()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached[0] == fingerprint:
                self._entries.move_to_end(key)
                self._hits += 1
                return cached[1], "hit", (time.perf_counter() - started) * 1000

        payload = builder()
        elapsed_ms = (time.perf_counter() - started) * 1000
        with self._lock:
            self._entries[key] = (fingerprint, payload)
            self._entries.move_to_end(key)
            self._misses += 1
            self._total_build_ms += elapsed_ms
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return payload, "miss", elapsed_ms

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            requests = self._hits + self._misses
            return {
                "entries": len(self._entries),
                "maximum_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "requests": requests,
                "hit_rate_pct": round(100 * self._hits / requests, 2) if requests else 0.0,
                "total_build_ms": round(self._total_build_ms, 2),
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
