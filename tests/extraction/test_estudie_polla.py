"""Deterministic extraction of journalist selections from synthetic magazines."""

import json
from io import BytesIO

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from benter_peru.extraction.estudie_polla import (
    EstudiePollaExtractionError,
    EstudiePollaExtractor,
)


def _pdf(*lines: str) -> BytesIO:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=letter)
    y = 740
    for line in lines:
        canvas.drawString(60, y, line)
        y -= 24
    canvas.save()
    stream.seek(0)
    return stream


def test_extracts_ordered_clear_picks_with_row_evidence() -> None:
    bundle = EstudiePollaExtractor().extract(
        _pdf(
            "REUNION 202647",
            "PRONÓSTICO DE LA REVISTA",
            "CARRERA | PERIODISTA | SELECCION",
            "1 | ESTUDIE SU POLLA | 3 MR. PEGGY, 1 SHOTRA, 5 VIEJO LINDO",
        )
    )

    assert bundle.requires_ocr is False
    assert len(bundle.facts) == 3
    payloads = [json.loads(fact.normalized_value) for fact in bundle.facts]
    assert [(item["rank"], item["mandil"], item["horse_name"]) for item in payloads] == [
        (1, 3, "MR. PEGGY"),
        (2, 1, "SHOTRA"),
        (3, 5, "VIEJO LINDO"),
    ]
    assert all(fact.evidence.page_number == 1 for fact in bundle.facts)
    assert all(fact.requires_review is False for fact in bundle.facts)


def test_ambiguous_pick_is_preserved_for_review_without_invented_mandil() -> None:
    bundle = EstudiePollaExtractor().extract(
        _pdf(
            "REUNION 202647",
            "PRONOSTICO DE LA REVISTA",
            "CARRERA | PERIODISTA | SELECCION",
            "2 | ESTUDIE SU POLLA | MR. PEGGY",
        )
    )

    assert len(bundle.facts) == 1
    payload = json.loads(bundle.facts[0].normalized_value)
    assert payload["mandil"] is None
    assert payload["horse_name"] == "MR. PEGGY"
    assert bundle.facts[0].requires_review is True
    assert bundle.facts[0].confidence < 0.8


def test_explicit_magazine_markers_without_rows_fail_closed() -> None:
    with pytest.raises(EstudiePollaExtractionError, match="no parseable selection rows"):
        EstudiePollaExtractor().extract(
            _pdf("REUNION 202647", "PRONOSTICO DE LA REVISTA", "SIN DATOS")
        )


def test_blank_magazine_requires_ocr() -> None:
    bundle = EstudiePollaExtractor().extract(_pdf())
    assert bundle.requires_ocr is True
    assert bundle.facts == ()
