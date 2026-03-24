"""SQLite connection and schema lifecycle (WAL for concurrent read/write)."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class Database:
    """
    Local SQLite database with WAL journaling.

    Writers use a single shared connection under :meth:`write_transaction` so
    commits are serialized while readers (e.g. search) open separate connections.
    WAL allows readers to see consistent snapshots during short write
    transactions.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._writer: sqlite3.Connection | None = None
        self._bootstrap_schema_file()

    def _bootstrap_schema_file(self) -> None:
        """Create tables and WAL on disk before any read-only search connection."""
        conn = sqlite3.connect(str(self.path), timeout=60.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            self._initialize_schema(conn)
            conn.commit()
        finally:
            conn.close()

    def _open_writer(self) -> sqlite3.Connection:
        if self._writer is None:
            conn = sqlite3.connect(
                str(self.path),
                timeout=60.0,
                check_same_thread=False,
                isolation_level=None,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._initialize_schema(conn)
            self._writer = conn
        return self._writer

    def _initialize_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                url TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                origin_url TEXT NOT NULL,
                depth INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS crawl_visited (
                url TEXT PRIMARY KEY
            );

            CREATE INDEX IF NOT EXISTS idx_documents_content ON documents (content);
            """
        )

    @contextmanager
    def write_transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Serialize writers; one short ``BEGIN IMMEDIATE`` … ``COMMIT`` per use.

        Safe to call from crawler worker threads; only one transaction runs at
        a time, matching a single-writer discipline with WAL readers.
        """
        with self._write_lock:
            conn = self._open_writer()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def connect_readonly(self) -> sqlite3.Connection:
        """
        Open a new connection for read queries (e.g. search).

        Uses URI mode read-only when possible; falls back to a normal connection
        with ``PRAGMA query_only`` for extra safety.
        """
        uri = self.path.resolve().as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=30.0)
        except sqlite3.Error:
            conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        """Close the shared writer connection."""
        with self._write_lock:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
