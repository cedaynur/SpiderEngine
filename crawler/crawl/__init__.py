"""Concurrent crawling, fetching, and URL management."""

from crawler.models import CrawledPage

from .crawler import WebCrawler, canonical_url
from .fetcher import FetchResult, HttpFetcher
from .parser import HtmlTextExtractor, LinkExtractor
from .throttle import RateLimiter
from .url_queue import BoundedUrlQueue
from .visited_registry import VisitedRegistry

__all__ = [
    "BoundedUrlQueue",
    "CrawledPage",
    "FetchResult",
    "HtmlTextExtractor",
    "HttpFetcher",
    "LinkExtractor",
    "RateLimiter",
    "VisitedRegistry",
    "WebCrawler",
    "canonical_url",
]
