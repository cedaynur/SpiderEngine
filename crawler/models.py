"""Domain models for crawl state and search results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrawledPage:
    """One fetched page: metadata plus optional plain text for indexing."""

    url: str
    depth: int
    origin_url: str
    status_code: int | None
    content_type: str | None
    text_content: str | None = None


@dataclass(frozen=True)
class SearchResult:
    """Single search hit: ``(relevant_url, origin_url, depth)`` per PRD."""

    relevant_url: str
    origin_url: str
    depth: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "relevant_url": self.relevant_url,
            "origin_url": self.origin_url,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class IndexedDocument:
    """Represents one indexed page and metadata for search."""

    url: str
    content: str
    origin_url: str
    depth: int


class CrawlJobState:
    """Persisted crawl session state for resume after interruption."""

    def __init__(self) -> None:
        pass
