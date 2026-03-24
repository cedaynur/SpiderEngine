"""Bounded URL work queue with back-pressure."""

from __future__ import annotations

import queue
from typing import Any, TypeVar

T = TypeVar("T")


class BoundedUrlQueue:
    """
    Thread-safe bounded FIFO queue for crawl tasks.

    A positive ``maxsize`` applies **back-pressure**: :meth:`put` blocks when the
    queue is full until consumers make room, throttling fast producers (workers
    that discover many links).
    """

    def __init__(self, maxsize: int) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1 for bounded back-pressure")
        self._maxsize = maxsize
        self._q: queue.Queue[T] = queue.Queue(maxsize=maxsize)

    @property
    def maxsize(self) -> int:
        """Configured capacity (blocking ``put`` when full)."""
        return self._maxsize

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        """
        Enqueue ``item``.

        With ``block=True`` (default), waits until space is available when full
        (**back-pressure**). With ``block=False``, raises ``queue.Full`` if full.
        """
        self._q.put(item, block=block, timeout=timeout)

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        """Remove and return the next item; may block when empty."""
        return self._q.get(block=block, timeout=timeout)

    def qsize(self) -> int:
        """Approximate number of queued items (may race with producers)."""
        return self._q.qsize()

    def is_full(self) -> bool:
        """True when the queue is at ``maxsize``."""
        return self._q.full()

    def is_empty(self) -> bool:
        """True when no items are waiting (may race with other threads)."""
        return self._q.empty()
