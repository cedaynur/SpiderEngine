"""Repositories for crawl-visit persistence (resume) and document storage."""

from __future__ import annotations

from .database import Database


class CrawlVisitRepository:
    """
    Persists URLs that have finished processing so a later crawl can skip them.

    Populated at the end of each URL worker task (after fetch / parse), so an
    interrupted fetch can be retried on resume.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    def load_all_urls(self) -> set[str]:
        """Return every URL recorded as visited in a prior session."""
        conn = self._db.connect_readonly()
        try:
            rows = conn.execute("SELECT url FROM crawl_visited").fetchall()
            return {str(r["url"]) for r in rows}
        finally:
            conn.close()

    def load_resume_skip_urls(self) -> set[str]:
        """
        URLs to treat as already crawled: finished visits plus indexed documents.

        Lets a new session skip work that was persisted before an interruption.
        """
        conn = self._db.connect_readonly()
        try:
            rows = conn.execute(
                """
                SELECT url FROM crawl_visited
                UNION
                SELECT url FROM documents
                """
            ).fetchall()
            return {str(r["url"]) for r in rows}
        finally:
            conn.close()

    def record_visited(self, canonical_url: str) -> None:
        """Insert or ignore a completed crawl URL (short transaction)."""
        with self._db.write_transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO crawl_visited (url) VALUES (?)",
                (canonical_url,),
            )


class IndexRepository:
    """Low-level document upserts used by :class:`crawler.search.indexer.Indexer`."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def upsert_document(
        self,
        url: str,
        content: str,
        origin_url: str,
        depth: int,
    ) -> None:
        """Store or replace a document row in one short transaction."""
        sql = """
            INSERT INTO documents (url, content, origin_url, depth)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                content = excluded.content,
                origin_url = excluded.origin_url,
                depth = excluded.depth
        """
        params = (url, content, origin_url, depth)
        with self._db.write_transaction() as conn:
            conn.execute(sql, params)
