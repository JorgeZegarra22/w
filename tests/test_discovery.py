"""Tests for explicit document discovery from publication HTML."""

from benter_peru.discovery import HtmlDocumentDiscoverer


def test_discovers_only_links_explicitly_typed_by_content_metadata() -> None:
    html = """
    <a href="/opaque/123" data-document-type="estudie_su_polla">Edición semanal</a>
    <a href="/looks-like-a-program.pdf">Un archivo no clasificado</a>
    """

    discovered = HtmlDocumentDiscoverer().discover(html, "https://example.test/ediciones/")

    assert len(discovered) == 1
    assert discovered[0].url == "https://example.test/opaque/123"
    assert discovered[0].document_type == "estudie_su_polla"
    assert discovered[0].link_context == "Edición semanal"


def test_ignores_non_http_and_empty_document_links() -> None:
    html = """
    <a data-document-type="programa" href="javascript:void(0)">Dinámico</a>
    <a data-document-type="programa" href="">Vacío</a>
    """

    assert HtmlDocumentDiscoverer().discover(html, "https://example.test/") == ()
