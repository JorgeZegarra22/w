"""Behavioral tests for whitespace-aligned horse-racing rows."""

import json
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from benter_peru.extraction.router import ExtractionRouter


def _program_pdf() -> BytesIO:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(35, 790, "1ra. CAR.- HANDICAP PARA TODO CABALLO")
    canvas.drawString(35, 765, 'CUADRUPLE "A" GANADOR PLACE')

    canvas.drawString(35, 735, "1")
    canvas.drawString(55, 735, "WAYTT")
    canvas.drawString(173, 735, "56.00 / 53")
    canvas.drawString(260, 735, "S.B.P.")
    canvas.drawString(342, 735, "J H SUAREZ")
    canvas.drawString(405, 735, "R Melgarejo")

    canvas.drawString(35, 715, "2")
    canvas.drawString(55, 715, "tNrzrAMo (usA)")
    canvas.drawString(173, 715, "54.00 / 51")
    canvas.drawString(260, 715, "JET SET")
    canvas.drawString(342, 715, "G A ROJAS")
    canvas.drawString(405, 715, "J A FLORES")

    canvas.drawString(35, 680, "2da. CAR.- SIGUIENTE CARRERA")
    canvas.save()
    stream.seek(0)
    return stream


def test_extracts_structured_first_race_rows_from_whitespace_columns() -> None:
    bundle = ExtractionRouter().extract(_program_pdf())

    assert len(bundle.facts) == 2
    first = bundle.facts[0]
    value = json.loads(first.normalized_value)
    assert value == {
        "horse_name": "WAYTT",
        "jockey": "J H SUAREZ",
        "mandil": 1,
        "trainer": "R Melgarejo",
        "weight": "56.00",
    }
    assert first.fact_type == "race_entry"
    assert first.subject_key == "race:1:mandil:1"
    assert first.evidence.page_number == 1
    assert first.evidence.bbox.x0 <= 35
    assert first.evidence.bbox.x1 > 430
    assert first.requires_review is False


def test_preserves_noisy_horse_name_and_requires_review() -> None:
    bundle = ExtractionRouter().extract(_program_pdf())

    noisy = bundle.facts[1]
    value = json.loads(noisy.normalized_value)
    assert value["horse_name"] == "tNrzrAMo (usA)"
    assert value["weight"] == "54.00"
    assert noisy.confidence < 0.8
    assert noisy.requires_review is True
