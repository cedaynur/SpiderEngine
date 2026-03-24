"""Concurrent-safe search over the current index (WAL + read connections)."""

from __future__ import annotations


from crawler.storage.database import Database
from crawler.search.relevancy import RelevancyScorer


def _escape_like(pattern: str) -> str:
    """Escape ``%``, ``_``, and ``\\`` for SQL ``LIKE`` with ``ESCAPE '\\'``."""
    return (
        pattern.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class SearchEngine:
    """
    Read-only search over indexed documents.

    Each :meth:`search` opens its own connection with ``PRAGMA query_only=ON``,
    so it can run safely while :class:`crawler.search.indexer.Indexer` commits
    on the writer (WAL allows concurrent readers).
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    def search(self, query: str, *, limit: int = 100) -> list[tuple[str, str, int, float]]:
        """
        Return up to ``limit`` hits as ``(relevant_url, origin_url, depth, score)``.

        Matching uses case-insensitive ``LIKE`` on ``content`` and ``url``.
        Results are ranked by relevancy.
        """
        q = (query or "").strip()
        if not q:
            return []

        esc = _escape_like(q)
        pattern = f"%{esc}%"
        conn = self._db.connect_readonly()
        try:
            cur = conn.execute(
                """
                SELECT url, origin_url, depth, (
                    LENGTH(lower(content)) - LENGTH(REPLACE(lower(content), lower(?), ''))
                ) / LENGTH(lower(?)) as frequency
                FROM documents
                WHERE lower(content) LIKE lower(?) ESCAPE '\\'
                   OR lower(url) LIKE lower(?) ESCAPE '\\'
                LIMIT ?
                """,
                (q, q, pattern, pattern, limit),
            )
            rows = cur.fetchall()
            raw_hits = [(str(r["url"]), str(r["origin_url"]), int(r["depth"]), int(r["frequency"])) for r in rows]
            scorer = RelevancyScorer()
            ranked_hits = scorer.rank_results(q, raw_hits)
            return ranked_hits
        finally:
            conn.close()

    def refresh_view(self) -> None:
        """Hook for future materialized views; WAL reads always see latest committed data."""
        return None
