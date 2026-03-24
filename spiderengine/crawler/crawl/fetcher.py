"""HTTP fetch using standard library only (per PRD)."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class FetchResult:
    """Outcome of a single GET request (redirects followed by default)."""

    url: str
    final_url: str
    status_code: int | None
    body: bytes | None
    content_type: str | None
    charset: str | None
    error: str | None


class HttpFetcher:
    """
    Fetches publicly accessible resources over HTTP/HTTPS using urllib.request.

    Handles timeouts, HTTP errors, and transport errors without raising to the
    crawler loop; callers inspect ``FetchResult.error`` and ``body``.
    """

    def __init__(
        self,
        *,
        timeout_sec: float = 30.0,
        user_agent: str = "AI-AidedCrawler/1.0",
        verify_tls: bool = True,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._user_agent = user_agent
        if verify_tls:
            self._ssl_context = ssl.create_default_context()
        else:
            self._ssl_context = ssl._create_unverified_context()

    def fetch(self, url: str) -> FetchResult:
        """
        Perform a GET request for ``url``.

        Returns a :class:`FetchResult` for every outcome, including failures.
        """
        request = Request(
            url,
            method="GET",
            headers={"User-Agent": self._user_agent},
        )
        try:
            with urlopen(
                request,
                timeout=self._timeout_sec,
                context=self._ssl_context,
            ) as response:
                final_url = getattr(response, "geturl", lambda: url)()
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                content_type = response.headers.get_content_type()
                if not content_type:
                    raw_ct = response.headers.get("Content-Type")
                    content_type = raw_ct.split(";")[0].strip() if raw_ct else None
                charset: str | None = None
                try:
                    charset = response.headers.get_content_charset()
                except Exception:
                    charset = None
                body = response.read()
                return FetchResult(
                    url=url,
                    final_url=final_url or url,
                    status_code=status,
                    body=body,
                    content_type=content_type,
                    charset=charset,
                    error=None,
                )
        except HTTPError as exc:
            body = exc.read() if exc.fp else None
            return FetchResult(
                url=url,
                final_url=exc.url if getattr(exc, "url", None) else url,
                status_code=exc.code,
                body=body,
                content_type=None,
                charset=None,
                error=f"HTTP {exc.code}",
            )
        except URLError as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                body=None,
                content_type=None,
                charset=None,
                error=str(exc.reason if getattr(exc, "reason", None) else exc),
            )
        except (TimeoutError, OSError) as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                body=None,
                content_type=None,
                charset=None,
                error=str(exc),
            )

    def close(self) -> None:
        """Reserved for custom openers; default fetcher has no persistent state."""
        return None
