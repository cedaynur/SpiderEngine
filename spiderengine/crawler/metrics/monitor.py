"""Thread-safe counters and snapshots for real-time UI."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricsSnapshot:
    """
    Point-in-time view for dashboards (PRD 6.3).

    * ``discovered_urls`` — unique URLs in the visited set (scheduled/crawled).
    * ``queue_depth`` — tasks waiting in :class:`~crawler.crawl.url_queue.BoundedUrlQueue`.
    * ``pending_tasks`` — outstanding work units (queue + in-flight worker tasks).
    * ``back_pressure`` — ``IDLE`` or ``THROTTLED`` when the queue is full and/or
      the global rate limiter is sleeping.
    """

    processed_urls: int
    discovered_urls: int
    queue_depth: int
    pending_tasks: int
    back_pressure: str
    throttle_detail: str

    def format_line(self) -> str:
        return (
            f"processed={self.processed_urls} "
            f"discovered={self.discovered_urls} "
            f"queued={self.queue_depth} "
            f"pending={self.pending_tasks} "
            f"| {self.back_pressure}"
            + (f" ({self.throttle_detail})" if self.throttle_detail else "")
        )


class MetricsMonitor:
    """
    Thread-safe crawl metrics.

    Workers increment ``processed_urls``; the UI thread (or REPL) calls
    :meth:`snapshot` with the live :class:`~crawler.crawl.crawler.WebCrawler` to
    merge queue depth, visited count, and back-pressure signals.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processed = 0
        self._rate_limited = False

    def increment_processed(self) -> None:
        """Count one URL whose worker task has finished (success or failure)."""
        with self._lock:
            self._processed += 1

    def set_queue_depth(self, _n: int) -> None:
        """Deprecated hook; queue depth is read live from the crawler in :meth:`snapshot`."""
        return None

    def set_back_pressure(self, _active: bool) -> None:
        """Deprecated hook; back-pressure is derived in :meth:`snapshot`."""
        return None

    def set_rate_limited(self, active: bool) -> None:
        """Called by :class:`~crawler.crawl.throttle.RateLimiter` while sleeping."""
        with self._lock:
            self._rate_limited = active

    def reset(self) -> None:
        """Clear counters before a new crawl session."""
        with self._lock:
            self._processed = 0
            self._rate_limited = False

    def snapshot(self, crawler: Any | None = None) -> MetricsSnapshot:
        """
        Build a snapshot, optionally pulling queue and visited stats from ``crawler``.

        If ``crawler`` is None, queue/discovered/pending default to 0.
        """
        with self._lock:
            processed = self._processed
            rate_on = self._rate_limited

        discovered = queue_depth = pending = 0
        queue_full = False
        if crawler is not None:
            try:
                queue_depth = crawler.work_queue.qsize()
                queue_full = crawler.work_queue.is_full()
                discovered = len(crawler.visited)
                pending = crawler.pending_task_count
            except Exception:
                pass

        reasons: list[str] = []
        if queue_full:
            reasons.append("queue_full")
        if rate_on:
            reasons.append("rate_limit")
        throttled = bool(reasons)
        detail = "+".join(reasons) if reasons else ""

        return MetricsSnapshot(
            processed_urls=processed,
            discovered_urls=discovered,
            queue_depth=queue_depth,
            pending_tasks=pending,
            back_pressure="THROTTLED" if throttled else "IDLE",
            throttle_detail=detail,
        )
