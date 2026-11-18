"""Route supported documents to deterministic extractors."""

from benter_peru.extraction.models import ExtractionBundle
from benter_peru.extraction.pdf_text import PdfSource, TextPdfExtractor


class ExtractionRouter:
    """Current PDF-only router; OCR remains deliberately unavailable."""

    def __init__(self, extractor: TextPdfExtractor | None = None) -> None:
        self._extractor = extractor or TextPdfExtractor()

    def extract(self, source: PdfSource) -> ExtractionBundle:
        return self._extractor.extract(source)
