"""Builds and updates the searchable index from crawled content."""

from __future__ import annotations

from crawler.models import CrawledPage
from crawler.storage.database import Database
from crawler.storage.repository import IndexRepository


class Indexer:
    """
    Persists :class:`CrawledPage` rows into SQLite (text + metadata).

    Uses the shared :class:`Database` write path so commits are short and
    serialized; readers (search) use WAL + separate connections.
    """

    def __init__(self, database: Database) -> None:
        self._db = database
        self._repo = IndexRepository(database)

    def index_page(self, page: CrawledPage) -> None:
        """
        Upsert ``page`` when ``text_content`` is present and non-empty.

        No-op for pages without extractable text (e.g. binary HTML edge cases).
        """
        text = (page.text_content or "").strip()
        if not text:
            return
        self._repo.upsert_document(
            url=page.url,
            content=text,
            origin_url=page.origin_url,
            depth=page.depth,
        )

    def remove_page(self, url: str) -> None:
        """Remove a document by canonical URL."""
        with self._db.write_transaction() as conn:
            conn.execute("DELETE FROM documents WHERE url = ?", (url,))

    def flush(self) -> None:
        """SQLite auto-commits per transaction; nothing to flush."""
        return None
