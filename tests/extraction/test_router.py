from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from benter_peru.extraction.router import ExtractionRouter


def text_pdf() -> BytesIO:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=letter)
    canvas.drawString(72, 720, "Caballo Ganador")
    canvas.save()
    buffer.seek(0)
    return buffer


def blank_pdf() -> BytesIO:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=letter)
    canvas.showPage()
    canvas.save()
    buffer.seek(0)
    return buffer


def test_extracts_page_text_and_bounding_box_from_text_layer() -> None:
    router = ExtractionRouter()

    bundle = router.extract(text_pdf())

    caballo = next(item for item in bundle.evidence if item.text == "Caballo")
    assert bundle.requires_ocr is False
    assert bundle.method == "text"
    assert caballo.page_number == 1
    assert caballo.confidence == 1.0
    assert caballo.requires_review is False
    assert caballo.bbox.x0 >= 0
    assert caballo.bbox.top >= 0
    assert caballo.bbox.x1 > caballo.bbox.x0
    assert caballo.bbox.bottom > caballo.bbox.top


def test_marks_blank_pdf_as_requiring_ocr_without_evidence() -> None:
    router = ExtractionRouter()

    bundle = router.extract(blank_pdf())

    assert bundle.requires_ocr is True
    assert bundle.method == "text"
    assert bundle.evidence == ()
