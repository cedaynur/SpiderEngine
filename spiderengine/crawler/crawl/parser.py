"""HTML parsing and hyperlink extraction using html.parser only."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _AnchorCollector(HTMLParser):
    """Collects raw ``href`` values from ``<a>`` start tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self._hrefs.append(value)


class LinkExtractor:
    """
    Extracts absolute http(s) hyperlinks from HTML for recursive crawling.

    Uses :class:`html.parser.HTMLParser` only (no third-party parsers).
    """

    def extract_links(
        self,
        html: bytes,
        base_url: str,
        *,
        charset: str | None = None,
    ) -> list[str]:
        """
        Decode ``html`` and return unique absolute ``http``/``https`` URLs.

        ``base_url`` resolves relative references (e.g. from the final URL
        after redirects). Malformed markup yields whatever links were seen
        before the parser stopped.
        """
        text = self._decode_html(html, charset)
        parser = _AnchorCollector()
        try:
            parser.feed(text)
            parser.close()
        except Exception:
            # Best-effort: still return partial link set on pathological input.
            pass

        seen: set[str] = set()
        out: list[str] = []
        for raw in parser._hrefs:
            candidate = raw.strip()
            if not candidate or candidate.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            absolute = urljoin(base_url, candidate)
            parsed = urlparse(absolute)
            if parsed.scheme.lower() not in ("http", "https"):
                continue
            if not parsed.netloc:
                continue
            if absolute not in seen:
                seen.add(absolute)
                out.append(absolute)
        return out

    @staticmethod
    def _decode_html(html: bytes, charset: str | None) -> str:
        for enc in (charset, "utf-8", "iso-8859-1"):
            if not enc:
                continue
            try:
                return html.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
        return html.decode("utf-8", errors="replace")


class _VisibleTextCollector(HTMLParser):
    """Collects human-visible text, skipping ``script`` and ``style`` subtrees."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._suppress = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in ("script", "style"):
            self._suppress += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("script", "style") and self._suppress > 0:
            self._suppress -= 1

    def handle_data(self, data: str) -> None:
        if self._suppress == 0 and data:
            self._parts.append(data)


class HtmlTextExtractor:
    """
    Strips markup to plain text using :class:`html.parser.HTMLParser` only.

    Used for document bodies stored in SQLite and searched via ``LIKE``.
    """

    @staticmethod
    def extract(html: bytes, charset: str | None = None) -> str:
        """Decode ``html`` and return normalized whitespace-stripped text."""
        text = LinkExtractor._decode_html(html, charset)
        parser = _VisibleTextCollector()
        try:
            parser.feed(text)
            parser.close()
        except Exception:
            pass
        raw = " ".join(parser._parts)
        return " ".join(raw.split())
