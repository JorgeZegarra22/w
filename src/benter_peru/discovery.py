"""Deterministic discovery from semantic link context, never filenames."""

import logging
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

LOGGER = logging.getLogger(__name__)


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
    download_url: str | None = None


class _SemanticLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self._active: tuple[str, str] | None = None
        self._context: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "a" and self._active is None:
            href = (attributes.get("href") or "").strip()
            if href:
                explicit_type = (attributes.get("data-document-type") or "").strip()
                self._active = (href, explicit_type)
                self._context = [
                    value.strip()
                    for name in ("aria-label", "title")
                    if (value := attributes.get(name)) and value.strip()
                ]
        elif tag.lower() == "img" and self._active is not None:
            alt = (attributes.get("alt") or "").strip()
            if alt:
                self._context.append(alt)

    def handle_data(self, data: str) -> None:
        if self._active is not None and data.strip():
            self._context.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._active is None:
            return
        href, explicit_type = self._active
        context = " ".join(" ".join(self._context).split())
        self.links.append((href, explicit_type, context))
        self._active = None
        self._context = []


class HtmlDocumentDiscoverer:
    """Classify publication links using explicit metadata or human-readable context."""

    def __init__(self, *, expected_types: tuple[str, ...] = ()) -> None:
        self._expected_types = expected_types

    def discover(self, html: str, base_url: str) -> tuple[DiscoveredDocument, ...]:
        parser = _SemanticLinkParser()
        parser.feed(html)
        discovered: list[DiscoveredDocument] = []
        for href, explicit_type, context in parser.links:
            url = urljoin(base_url, href)
            if urlsplit(url).scheme not in {"http", "https"}:
                continue
            document_type = explicit_type or self._classify(context)
            if not document_type:
                continue
            discovered.append(
                DiscoveredDocument(
                    url=url,
                    document_type=document_type,
                    link_context=context,
                    download_url=self._download_url(url),
                )
            )

        found_types = {item.document_type for item in discovered}
        for expected_type in self._expected_types:
            if expected_type not in found_types:
                LOGGER.warning(
                    "expected document link not found on source surface: %s",
                    expected_type,
                    extra={"document_type": expected_type, "base_url": base_url},
                )
        return tuple(discovered)

    @staticmethod
    def _classify(context: str) -> str | None:
        normalized = unicodedata.normalize("NFKD", context).encode("ascii", "ignore").decode()
        words = " ".join(re.sub(r"[^a-z0-9]+", " ", normalized.lower()).split())
        if "estudie su polla" in words:
            return "estudie_su_polla"
        if "prog monterrico" in words or "programa monterrico" in words:
            return "programa_monterrico"
        return None

    @staticmethod
    def _download_url(url: str) -> str | None:
        parsed = urlsplit(url)
        if parsed.netloc.lower() != "drive.google.com":
            return None
        match = re.fullmatch(r"/file/d/([^/]+)/view/?", parsed.path)
        if match is None:
            return None
        query = urlencode({"export": "download", "id": match[1]})
        return f"https://drive.google.com/uc?{query}"
