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
    canvas.drawString(450, 825, "REUNION 202647")
    canvas.drawString(35, 810, "PROGRAMA PARA LAS CARRERAS DEL SABADO 21 DE NOVIEMBRE 2026")
    canvas.drawString(35, 790, "1ra. CAR.- HANDICAP PARA TODO CABALLO")
    canvas.drawString(250, 790, "DISTANCIA 1,000 METROS ARENA")
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


def _multi_race_program_pdf() -> BytesIO:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(450, 825, "REUNION 202647")
    canvas.drawString(35, 810, "PROGRAMA PARA LAS CARRERAS DEL SABADO 21 DE NOVIEMBRE 2026")
    canvas.drawString(35, 790, "1ra. CAR.- HANDICAP")
    canvas.drawString(250, 790, "DISTANCIA 1,000 METROS ARENA")
    for y, mandil, horse in ((735, "1", "ALPHA"), (715, "2", "BETA")):
        canvas.drawString(35, y, mandil)
        canvas.drawString(55, y, horse)
        canvas.drawString(173, y, "56.00 / 53")
        canvas.drawString(260, y, "STUD A")
        canvas.drawString(342, y, "JOCKEY A")
        canvas.drawString(405, y, "TRAINER A")
    canvas.drawString(35, 680, "2da. CAR.- HANDICAP")
    canvas.drawString(250, 680, "DISTANCIA 1,400 METROS CESPED")
    for y, mandil, horse in ((640, "1", "GAMMA"), (620, "2", "DELTA")):
        canvas.drawString(35, y, mandil)
        canvas.drawString(55, y, horse)
        canvas.drawString(173, y, "54.00 / 51")
        canvas.drawString(260, y, "STUD B")
        canvas.drawString(342, y, "JOCKEY B")
        canvas.drawString(405, y, "TRAINER B")
    canvas.drawString(35, 580, "3ra. CAR.- SIGUIENTE")
    canvas.save()
    stream.seek(0)
    return stream


def _multi_page_program_pdf() -> BytesIO:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(450, 825, "REUNION 202647")
    canvas.drawString(35, 810, "PROGRAMA DEL SABADO 21 DE NOVIEMBRE 2026")
    canvas.drawString(35, 790, "1ra. CAR.- DISTANCIA 1,000 METROS ARENA")
    canvas.drawString(35, 735, "1")
    canvas.drawString(55, 735, "ALPHA")
    canvas.drawString(173, 735, "56.00 / 53")
    canvas.drawString(260, 735, "STUD A")
    canvas.drawString(342, 735, "JOCKEY A")
    canvas.drawString(405, 735, "TRAINER A")
    canvas.showPage()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(35, 790, "2da. CAR.- DISTANCIA 1,400 METROS CESPED")
    canvas.drawString(35, 735, "1")
    canvas.drawString(55, 735, "GAMMA")
    canvas.drawString(173, 735, "54.00 / 51")
    canvas.drawString(260, 735, "STUD B")
    canvas.drawString(342, 735, "JOCKEY B")
    canvas.drawString(405, 735, "TRAINER B")
    canvas.save()
    stream.seek(0)
    return stream


def test_extracts_structured_first_race_rows_from_whitespace_columns() -> None:
    bundle = ExtractionRouter().extract(_program_pdf())

    entries = [fact for fact in bundle.facts if fact.fact_type == "race_entry"]
    assert len(entries) == 2
    first = entries[0]
    value = json.loads(first.normalized_value)
    assert value == {
        "horse_name": "WAYTT",
        "jockey": "J H SUAREZ",
        "mandil": 1,
            "race_number": 1,
        "stud": "S.B.P.",
        "trainer": "R Melgarejo",
        "weight": "56.00",
        "horse_requires_review": False,
    }
    assert first.fact_type == "race_entry"
    assert first.subject_key == "race:1:mandil:1"
    assert first.evidence.page_number == 1
    assert first.evidence.bbox.x0 <= 35
    assert first.evidence.bbox.x1 > 430
    assert first.requires_review is False


def test_preserves_noisy_horse_name_and_requires_review() -> None:
    bundle = ExtractionRouter().extract(_program_pdf())

    noisy = [fact for fact in bundle.facts if fact.fact_type == "race_entry"][1]
    value = json.loads(noisy.normalized_value)
    assert value["horse_name"] == "tNrzrAMo (usA)"
    assert value["weight"] == "54.00"
    assert noisy.confidence < 0.8
    assert noisy.requires_review is True


def test_extracts_first_race_context_from_program_headers() -> None:
    bundle = ExtractionRouter().extract(_program_pdf())

    context = next(fact for fact in bundle.facts if fact.fact_type == "race_context")
    assert json.loads(context.normalized_value) == {
        "distance_meters": 1000,
        "meeting_code": "202647",
        "race_number": 1,
        "scheduled_date": "2026-11-21",
        "surface": "arena",
    }
    assert context.subject_key == "meeting:202647:race:1"
    assert context.evidence.page_number == 1


def test_extracts_every_complete_race_with_dynamic_context() -> None:
    bundle = ExtractionRouter().extract(_multi_race_program_pdf())

    contexts = [
        json.loads(fact.normalized_value)
        for fact in bundle.facts
        if fact.fact_type == "race_context"
    ]
    entries = [
        json.loads(fact.normalized_value)
        for fact in bundle.facts
        if fact.fact_type == "race_entry"
    ]

    assert contexts == [
        {
            "distance_meters": 1000,
            "meeting_code": "202647",
            "race_number": 1,
            "scheduled_date": "2026-11-21",
            "surface": "arena",
        },
        {
            "distance_meters": 1400,
            "meeting_code": "202647",
            "race_number": 2,
            "scheduled_date": "2026-11-21",
            "surface": "cesped",
        },
    ]
    assert [(entry["race_number"], entry["horse_name"]) for entry in entries] == [
        (1, "ALPHA"),
        (1, "BETA"),
        (2, "GAMMA"),
        (2, "DELTA"),
    ]


def test_reuses_document_header_context_across_pdf_pages() -> None:
    bundle = ExtractionRouter().extract(_multi_page_program_pdf())

    contexts = [
        json.loads(fact.normalized_value)
        for fact in bundle.facts
        if fact.fact_type == "race_context"
    ]

    assert [(item["race_number"], item["distance_meters"]) for item in contexts] == [
        (1, 1000),
        (2, 1400),
    ]
