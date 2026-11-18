"""Tests for explicit document discovery from publication HTML."""

import logging

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


def test_classifies_real_links_from_visible_text_and_accessible_context() -> None:
    html = """
    <a href="https://drive.google.com/file/d/program-id/view">PROG- MONTERRICO</a>
    <a href="/edition" aria-label="Abrir Estudie su Polla"><img alt="Edición semanal"></a>
    """

    discovered = HtmlDocumentDiscoverer().discover(html, "https://example.test/")

    assert [(item.document_type, item.link_context) for item in discovered] == [
        ("programa_monterrico", "PROG- MONTERRICO"),
        ("estudie_su_polla", "Abrir Estudie su Polla Edición semanal"),
    ]
    assert discovered[0].download_url == (
        "https://drive.google.com/uc?export=download&id=program-id"
    )


def test_warns_cleanly_when_expected_estudie_link_is_absent(caplog) -> None:
    html = '<a href="/program">PROG-MONTERRICO</a>'
    discoverer = HtmlDocumentDiscoverer(expected_types=("estudie_su_polla",))

    with caplog.at_level(logging.WARNING):
        discovered = discoverer.discover(html, "https://example.test/")

    assert len(discovered) == 1
    assert "estudie_su_polla" in caplog.text
    assert "not found" in caplog.text
