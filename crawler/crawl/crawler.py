"""Parallel web crawl up to depth *k* with back-pressure and a worker pool."""

from __future__ import annotations

import queue
import threading
from typing import Any
from urllib.parse import urldefrag, urlparse, urlunparse

from crawler.config import CrawlConfig
from crawler.models import CrawledPage
from crawler.metrics import MetricsMonitor
from crawler.storage.database import Database
from crawler.storage.repository import CrawlVisitRepository

from .fetcher import HttpFetcher
from .parser import HtmlTextExtractor, LinkExtractor
from .throttle import RateLimiter
from .url_queue import BoundedUrlQueue
from .visited_registry import VisitedRegistry


def canonical_url(url: str) -> str:
    """
    Normalize an absolute URL for stable deduplication keys.

    Strips fragments, lowercases scheme and host, and ensures a non-empty path.
    """
    cleaned = url.strip()
    cleaned, _frag = urldefrag(cleaned)
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL must be absolute with scheme and host: {url!r}")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


class WebCrawler:
    """
    Runs a BFS crawl from ``origin_url`` up to ``max_depth`` using a pool of
    worker threads.

    * **Worker pool:** ``max_workers`` threads dequeue URLs concurrently.
    * **Back-pressure:** :class:`BoundedUrlQueue` has a fixed ``maxsize``;
      :meth:`BoundedUrlQueue.put` blocks when full so producers slow down.
    * **Visited set:** :class:`VisitedRegistry` uses a :class:`threading.Lock`
      internally so concurrent ``try_mark_visited`` calls are safe.
    * **Rate limit:** ``fetch_delay_sec`` enforces a minimum spacing between
      fetches globally (shared :class:`RateLimiter`).
    * **Stop:** :meth:`stop` sets a shutdown flag; workers finish their current
      task, skip scheduling new URLs, then exit once the queue drains.

    Optional ``database`` enables **resume**: URLs in ``crawl_visited`` or
    ``documents`` are merged into the visited set before the crawl starts.
    Optional ``indexer`` persists HTML text and metadata for search.
    """

    def __init__(
        self,
        config: CrawlConfig,
        *,
        fetcher: HttpFetcher | None = None,
        extractor: LinkExtractor | None = None,
        visited: VisitedRegistry | None = None,
        work_queue: BoundedUrlQueue | None = None,
        database: Database | None = None,
        visit_repository: CrawlVisitRepository | None = None,
        indexer: Any = None,
        metrics: MetricsMonitor | None = None,
    ) -> None:
        self._config = config
        self._fetcher = fetcher or HttpFetcher(
            timeout_sec=config.fetch_timeout_sec,
            user_agent=config.user_agent,
            verify_tls=config.verify_tls,
        )
        self._extractor = extractor or LinkExtractor()
        self._visited = visited or VisitedRegistry()
        self._work_queue = work_queue or BoundedUrlQueue(maxsize=config.max_queue_size)
        self._metrics = metrics
        self._rate_limiter = RateLimiter(
            config.fetch_delay_sec,
            metrics_monitor=metrics,
        )

        self._database = database
        if visit_repository is not None:
            self._visit_repo = visit_repository
        elif database is not None:
            self._visit_repo = CrawlVisitRepository(database)
        else:
            self._visit_repo = None

        self._indexer = indexer

        self._shutdown = threading.Event()
        self._threads: list[threading.Thread] = []

        self._state_lock = threading.Lock()
        self._state_cv = threading.Condition(self._state_lock)
        self._remaining_tasks = 0

        self._pages: list[CrawledPage] = []
        self._pages_lock = threading.Lock()

        self._run_lock = threading.Lock()
        self._crawl_active = False

    @property
    def visited(self) -> VisitedRegistry:
        """Session visit registry (shared if injected from outside)."""
        return self._visited

    @property
    def work_queue(self) -> BoundedUrlQueue:
        """Bounded task queue (for metrics / UI)."""
        return self._work_queue

    @property
    def pending_task_count(self) -> int:
        """Outstanding tasks: queued work plus URLs currently being processed."""
        with self._state_lock:
            return self._remaining_tasks

    def start(self) -> None:
        """Clear shutdown so a subsequent :meth:`run` can proceed."""
        self._shutdown.clear()

    def stop(self) -> None:
        """
        Request graceful shutdown: workers stop enqueueing new URLs and exit
        after draining remaining work.
        """
        self._shutdown.set()

    def pause(self) -> None:
        """Placeholder for future pause/resume support."""
        pass

    def resume(self) -> None:
        """Placeholder for future pause/resume support."""
        pass

    def set_concurrency(self, max_workers: int) -> None:
        """
        Set ``max_workers`` for the **next** crawl.

        Raises :class:`RuntimeError` if a crawl is already running.
        """
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        with self._run_lock:
            if self._crawl_active:
                raise RuntimeError("Cannot change max_workers while a crawl is active")
        self._config.max_workers = max_workers

    def run_until_idle(self) -> list[CrawledPage]:
        """Same as :meth:`run`."""
        return self.run()

    def run(self) -> list[CrawledPage]:
        """
        Execute the crawl until the queue is drained and all tasks finish, or
        until :meth:`stop` has been called and remaining work completes.

        Thread-safe: do not call :meth:`run` concurrently from multiple threads.
        """
        self._config.validate()
        with self._run_lock:
            if self._crawl_active:
                raise RuntimeError("A crawl is already running on this WebCrawler instance")
            self._crawl_active = True

        self._shutdown.clear()
        self._pages.clear()
        self._visited.clear()

        with self._state_lock:
            self._remaining_tasks = 0

        if self._visit_repo is not None:
            self._visited.merge_urls(self._visit_repo.load_resume_skip_urls())

        seed = canonical_url(self._config.origin_url)
        origin_for_results = seed

        if self._visited.try_mark_visited(seed):
            self._schedule(seed, 0)

        self._threads = []
        for i in range(self._config.max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"CrawlWorker-{i}",
                args=(origin_for_results,),
                daemon=True,
            )
            t.start()
            self._threads.append(t)

        try:
            with self._state_lock:
                while self._remaining_tasks > 0:
                    self._state_cv.wait(timeout=0.5)
        finally:
            self._shutdown.set()
            for t in self._threads:
                t.join(timeout=30.0)
            self._threads.clear()
            with self._run_lock:
                self._crawl_active = False

        with self._pages_lock:
            return list(self._pages)

    def _schedule(self, url: str, depth: int) -> None:
        """Increment outstanding work and enqueue (may block on full queue)."""
        with self._state_lock:
            self._remaining_tasks += 1
        try:
            self._work_queue.put((url, depth), block=True)
        except Exception:
            with self._state_lock:
                self._remaining_tasks -= 1
                if self._remaining_tasks <= 0:
                    self._state_cv.notify_all()
            raise

    def _task_finished(self) -> None:
        with self._state_lock:
            self._remaining_tasks -= 1
            if self._remaining_tasks <= 0:
                self._state_cv.notify_all()

    def _worker_loop(self, origin_for_results: str) -> None:
        while True:
            if self._shutdown.is_set():
                with self._state_lock:
                    if self._remaining_tasks == 0 and self._work_queue.is_empty():
                        return

            try:
                url, depth = self._work_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._process_url(url, depth, origin_for_results)
            finally:
                self._task_finished()


    def _process_url(self, url: str, depth: int, origin_for_results: str) -> None:
        try:
            self._rate_limiter.wait_if_needed()

            result = self._fetcher.fetch(url)
            # DEBUG LOG: Fetch sonucu
            print(f"[FETCH-DEBUG] URL: {url} | Status: {result.status_code} | Error: {result.error}")

            if (
                result.error is None
                and result.body is not None
                and _is_probably_html(result.content_type)
            ):
                text_content = HtmlTextExtractor.extract(result.body, result.charset)
                page = CrawledPage(
                    url=url,
                    depth=depth,
                    origin_url=origin_for_results,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    text_content=text_content or None,
                )
                with self._pages_lock:
                    self._pages.append(page)
                if self._indexer is not None and text_content:
                    self._indexer.index_page(page)

            if self._shutdown.is_set():
                return

            if result.error is not None or result.body is None:
                print(f"[DEBUG] Fetch failed: {url} | error={result.error}")
                return

            if not _is_probably_html(result.content_type):
                print(f"[DEBUG] Not HTML: {url} | content_type={result.content_type}")
                return

            if depth >= self._config.max_depth:
                print(f"[DEBUG] Max depth reached: {url} | depth={depth}")
                return

            base = result.final_url or url
            links = self._extractor.extract_links(
                result.body,
                base,
                charset=result.charset,
            )
            for link in links:
                if self._shutdown.is_set():
                    return
                try:
                    child = canonical_url(link)
                except ValueError:
                    continue
                if self._visited.try_mark_visited(child):
                    self._schedule(child, depth + 1)
        finally:
            if self._metrics is not None:
                self._metrics.increment_processed()
            if self._visit_repo is not None:
                self._visit_repo.record_visited(url)


def _is_probably_html(content_type: str | None) -> bool:
    if not content_type:
        return False
    main = content_type.split(";")[0].strip().lower()
    return main in ("text/html", "application/xhtml+xml")
