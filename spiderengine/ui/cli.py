"""Command-line UI: index, search, live metrics (PRD 6.3)."""

from __future__ import annotations

import shlex
import sys
import threading
from pathlib import Path
from typing import TextIO

from crawler.config import DEFAULT_SQLITE_PATH, CrawlConfig
from crawler.crawl import WebCrawler
from crawler.metrics import MetricsMonitor
from crawler.search import Indexer, SearchEngine
from crawler.storage import Database

from .runtime import AppRuntime


class CliApplication:
    """
    Interactive REPL for crawl + search with a background metrics ticker.

    * ``index <url> <k>`` — start a crawl (depth *k*) in a worker thread; SQLite
      index is updated for search. Live ``[metrics]`` lines print about once
      per second while a crawl is active.
    * ``search <query>`` — run :class:`~crawler.search.engine.SearchEngine`
      against the database (safe while indexing thanks to WAL + read
      connections).
    * ``stop`` — cooperative :meth:`~crawler.crawl.crawler.WebCrawler.stop`.
    * ``status`` — one-shot metrics snapshot.

    Pass a shared :class:`AppRuntime` (with the Web UI) so metrics and DB stay
    in sync. When ``close_database_on_exit`` is False, the caller must
    :meth:`~crawler.storage.database.Database.close` after shutting down HTTP.
    """

    def __init__(
        self,
        runtime: AppRuntime | None = None,
        *,
        database_path: str | Path | None = None,
        out: TextIO | None = None,
        close_database_on_exit: bool = True,
    ) -> None:
        self._out = out or sys.stdout
        self._close_database_on_exit = close_database_on_exit
        if runtime is not None:
            self._rt = runtime
        else:
            db = Database(database_path or DEFAULT_SQLITE_PATH)
            self._rt = AppRuntime(db, MetricsMonitor())
        self._print_lock = threading.Lock()
        self._repl_shutdown = threading.Event()
        self._crawl_thread: threading.Thread | None = None

    @property
    def runtime(self) -> AppRuntime:
        return self._rt

    def _println(self, message: str = "") -> None:
        with self._print_lock:
            print(message, file=self._out, flush=True)

    def run(self) -> None:
        """Start the metrics ticker and the command loop until ``quit`` / EOF."""
        self._repl_shutdown.clear()
        metrics_thread = threading.Thread(
            target=self._metrics_loop,
            name="MetricsTicker",
            daemon=True,
        )
        metrics_thread.start()
        self._println(
            "AI-Aided Crawler & Search — commands: index <url> <k> | search <query> | "
            "status | stop | help | quit"
        )
        self._println(f"Database: {self._rt.database.path}")
        try:
            while True:
                try:
                    line = input("crawler> ")
                except EOFError:
                    self._println()
                    break
                except KeyboardInterrupt:
                    self._println("\n(Interrupted — type 'quit' to exit or continue.)")
                    continue
                if not self._dispatch(line.strip()):
                    break
        finally:
            self._repl_shutdown.set()
            crawler = self._rt.get_active_crawler()
            if crawler is not None:
                crawler.stop()
            if self._crawl_thread is not None and self._crawl_thread.is_alive():
                self._crawl_thread.join(timeout=35.0)
            if self._close_database_on_exit:
                self._rt.database.close()

    def _metrics_loop(self) -> None:
        while True:
            if self._repl_shutdown.wait(timeout=1.0):
                break
            if not self._rt.is_crawl_running():
                continue
            crawler = self._rt.get_active_crawler()
            if crawler is None:
                continue
            snap = self._rt.metrics.snapshot(crawler)
            with self._print_lock:
                print(f"[metrics] {snap.format_line()}", file=self._out, flush=True)

    def _dispatch(self, line: str) -> bool:
        """Return False to exit the REPL."""
        if not line:
            return True
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            self._println(f"Parse error: {exc}")
            return True
        cmd = parts[0].lower()
        if cmd in ("quit", "exit", "q"):
            return False
        if cmd == "help":
            self._cmd_help()
        elif cmd == "index":
            self._cmd_index(parts)
        elif cmd == "search":
            self._cmd_search(parts)
        elif cmd == "status":
            self._cmd_status()
        elif cmd == "stop":
            self._cmd_stop()
        else:
            self._println(f"Unknown command {cmd!r}. Type 'help'.")
        return True

    def _cmd_help(self) -> None:
        self._println(
            "  index <url> <k>   Start crawl from origin URL to max depth k (runs in background).\n"
            "  search <query>  Search indexed text (works while a crawl is running).\n"
            "  status          Print one metrics line (processed / discovered / queue / pressure).\n"
            "  stop            Ask the crawler to finish gracefully (no new URLs enqueued).\n"
            "  quit            Exit the program."
        )

    def _cmd_index(self, parts: list[str]) -> None:
        if len(parts) < 3:
            self._println("Usage: index <url> <k>   (example: index http://example.com 1)")
            return
        if self._rt.is_crawl_running():
            self._println("A crawl is already running. Use 'stop' first or wait until it finishes.")
            return
        url = parts[1]
        try:
            k = int(parts[2])
        except ValueError:
            self._println("Depth k must be an integer.")
            return
        try:
            cfg = CrawlConfig(origin_url=url, max_depth=k)
            cfg.validate()
        except ValueError as exc:
            self._println(f"Invalid crawl config: {exc}")
            return

        self._rt.metrics.reset()
        indexer = Indexer(self._rt.database)
        crawler = WebCrawler(
            cfg,
            database=self._rt.database,
            indexer=indexer,
            metrics=self._rt.metrics,
        )
        self._rt.set_crawl_active(crawler, True)


        def crawl_job() -> None:
            try:
                pages = crawler.run()
                self._println(f"[crawl] Done. HTML pages fetched this run: {len(pages)}.")
                
                try:
                    from export_data import export_to_pdata
                    export_to_pdata()
                    self._println("[export] p.data has been generated successfully.")
                except ImportError:
                    self._println("[export] Error: export_data.py not found in path.")
                except Exception as e:
                    self._println(f"[export] Failed to update p.data: {e}")
            except Exception as exc:
                self._println(f"[crawl] Error: {exc}")
            finally:
                self._rt.set_crawl_active(None, False)

        self._crawl_thread = threading.Thread(target=crawl_job, name="CrawlJob", daemon=True)
        self._crawl_thread.start()
        self._println(
            "[crawl] Started in background. [metrics] lines will appear while it runs. "
            "You can run 'search <query>' anytime."
        )

    def _cmd_search(self, parts: list[str]) -> None:
        if len(parts) < 2:
            self._println("Usage: search <query>")
            return
        query = " ".join(parts[1:]).strip()
        if not query:
            self._println("Usage: search <query>")
            return
        engine = SearchEngine(self._rt.database)
        hits = engine.search(query, limit=50)
        if not hits:
            self._println("(no results)")
            return
        for rel, origin, depth in hits:
            self._println(f"  {rel}  |  origin={origin}  |  depth={depth}")

    def _cmd_status(self) -> None:
        snap = self._rt.metrics.snapshot(self._rt.get_active_crawler())
        self._println(snap.format_line())

    def _cmd_stop(self) -> None:
        crawler = self._rt.get_active_crawler()
        if crawler is None:
            self._println("No active crawler.")
            return
        crawler.stop()
        self._println("Stop requested — crawler will drain without enqueueing new URLs.")

    def render_metrics(self) -> None:
        """Print a single snapshot (same as the ``status`` command)."""
        self._cmd_status()
