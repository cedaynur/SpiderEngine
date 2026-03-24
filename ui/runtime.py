"""Shared process state for CLI and Web UI (database, metrics, active crawler)."""

from __future__ import annotations

import threading

from crawler.crawl.crawler import WebCrawler
from crawler.metrics import MetricsMonitor
from crawler.storage import Database


class AppRuntime:
    """
    Thread-safe bridge so the HTTP server (worker threads) and CLI agree on
    which :class:`~crawler.crawl.crawler.WebCrawler` is active and share one
    :class:`~crawler.storage.database.Database` and :class:`MetricsMonitor`.
    """

    def __init__(self, database: Database, metrics: MetricsMonitor) -> None:
        self.database = database
        self.metrics = metrics
        self._lock = threading.Lock()
        self._active_crawler: WebCrawler | None = None
        self._crawl_running = False

    def get_active_crawler(self) -> WebCrawler | None:
        with self._lock:
            return self._active_crawler

    def is_crawl_running(self) -> bool:
        with self._lock:
            return self._crawl_running

    def set_crawl_active(self, crawler: WebCrawler | None, running: bool) -> None:
        with self._lock:
            self._active_crawler = crawler
            self._crawl_running = running

    def metrics_snapshot_dict(self) -> dict[str, str | int | bool]:
        """JSON-serializable metrics for ``/api/metrics``."""
        with self._lock:
            crawler = self._active_crawler
            crawl_running = self._crawl_running
        snap = self.metrics.snapshot(crawler)
        return {
            "processed_urls": snap.processed_urls,
            "discovered_urls": snap.discovered_urls,
            "queue_depth": snap.queue_depth,
            "pending_tasks": snap.pending_tasks,
            "back_pressure": snap.back_pressure,
            "throttle_detail": snap.throttle_detail,
            "crawl_running": crawl_running,
        }
