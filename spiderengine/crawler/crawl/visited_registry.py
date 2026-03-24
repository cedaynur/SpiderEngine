"""Per-session URL deduplication."""

from __future__ import annotations

import threading
from typing import Iterable


class VisitedRegistry:
    """
    Ensures each canonical URL is crawled at most once per session.

    All reads and writes of the internal set are serialized with a
    :class:`threading.Lock` so concurrent workers never race when recording
    visits (PRD / .cursorrules thread-safety).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._urls: set[str] = set()

    @property
    def lock(self) -> threading.Lock:
        """The mutex guarding ``_urls``; prefer :meth:`try_mark_visited` for updates."""
        return self._lock

    def try_mark_visited(self, canonical_url: str) -> bool:
        """
        If ``canonical_url`` is new, record it and return True.

        If it was already recorded this session, return False.
        """
        with self._lock:
            if canonical_url in self._urls:
                return False
            self._urls.add(canonical_url)
            return True

    def was_visited(self, canonical_url: str) -> bool:
        """Return True if this canonical URL was already marked visited."""
        with self._lock:
            return canonical_url in self._urls

    def clear(self) -> None:
        """Drop all visit records (e.g. before a new crawl session)."""
        with self._lock:
            self._urls.clear()

    def merge_urls(self, urls: Iterable[str]) -> None:
        """Union persisted URLs into the in-memory set (crawl resume)."""
        with self._lock:
            self._urls.update(urls)

    def __len__(self) -> int:
        """Number of unique URLs recorded in the visited set."""
        with self._lock:
            return len(self._urls)
