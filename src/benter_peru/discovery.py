"""Deterministic discovery of explicitly classified document links."""

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    code: str
    name: str
    base_url: str
    index_url: str
    rate_limit_ms: int = 0


@dataclass(frozen=True, slots=True)
class DiscoveredDocument:
    url: str
    document_type: str
    link_context: str


class _TypedLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self._active: tuple[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._active is not None:
            return
        attributes = dict(attrs)
        href = (attributes.get("href") or "").strip()
        document_type = (attributes.get("data-document-type") or "").strip()
        if href and document_type:
            self._active = (href, document_type)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._active is None:
            return
        href, document_type = self._active
        context = " ".join("".join(self._text).split())
        self.links.append((href, document_type, context))
        self._active = None
        self._text = []


class HtmlDocumentDiscoverer:
    """Discover documents from semantic link metadata, never from filenames."""

    def discover(self, html: str, base_url: str) -> tuple[DiscoveredDocument, ...]:
        parser = _TypedLinkParser()
        parser.feed(html)
        discovered: list[DiscoveredDocument] = []
        for href, document_type, context in parser.links:
            url = urljoin(base_url, href)
            if urlsplit(url).scheme not in {"http", "https"}:
                continue
            discovered.append(DiscoveredDocument(url, document_type, context))
        return tuple(discovered)
