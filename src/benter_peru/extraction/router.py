"""Route supported documents to deterministic extractors."""

from benter_peru.extraction.estudie_polla import EstudiePollaExtractor
from benter_peru.extraction.models import ExtractionBundle
from benter_peru.extraction.pdf_text import PdfSource, TextPdfExtractor


class ExtractionRouter:
    """Current PDF-only router; OCR remains deliberately unavailable."""

    def __init__(
        self,
        extractor: TextPdfExtractor | None = None,
        magazine_extractor: EstudiePollaExtractor | None = None,
    ) -> None:
        self._extractor = extractor or TextPdfExtractor()
        self._magazine_extractor = magazine_extractor or EstudiePollaExtractor()

    def extract(
        self, source: PdfSource, *, document_type: str = "programa_monterrico"
    ) -> ExtractionBundle:
        if document_type == "estudie_su_polla":
            return self._magazine_extractor.extract(source)
        return self._extractor.extract(source)
