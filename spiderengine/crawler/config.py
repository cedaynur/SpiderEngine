"""Crawl and application configuration."""

from dataclasses import dataclass
from pathlib import Path

# Repository root (parent of the `crawler` package); SQLite lives in `data/`.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = _PROJECT_ROOT / "data"
DEFAULT_SQLITE_PATH = DATA_DIR / "crawler.db"


@dataclass
class CrawlConfig:
    """Limits for crawl depth, fetch behavior, and queue sizing."""

    origin_url: str
    max_depth: int
    max_queue_size: int = 100_000
    max_workers: int = 8
    fetch_timeout_sec: float = 30.0
    fetch_delay_sec: float = 0.05
    user_agent: str = "AI-AidedCrawler/1.0 (+https://example.edu/crawler)"
    verify_tls: bool = True

    def validate(self) -> None:
        """Raise ValueError if configuration is unusable for a crawl."""
        if not (self.origin_url or "").strip():
            raise ValueError("origin_url must be non-empty")
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if self.max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")
        if self.max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if self.fetch_timeout_sec <= 0:
            raise ValueError("fetch_timeout_sec must be positive")
        if self.fetch_delay_sec < 0:
            raise ValueError("fetch_delay_sec must be non-negative")


@dataclass
class AppConfig:
    """Top-level application settings (database path, UI mode, etc.)."""

    database_path: Path = DEFAULT_SQLITE_PATH

    def validate(self) -> None:
        pass
