"""Text-layer PDF extraction using pdfplumber word coordinates."""

from pathlib import Path
from typing import BinaryIO

import pdfplumber

from benter_peru.extraction.models import BoundingBox, ExtractionBundle, TextEvidence

type PdfSource = str | Path | BinaryIO


class TextPdfExtractor:
    """Extract word evidence from machine-generated PDFs without OCR."""

    def extract(self, source: PdfSource) -> ExtractionBundle:
        evidence: list[TextEvidence] = []
        # pdfplumber accepts seekable binary streams at runtime, while its public
        # type annotation enumerates only a subset of BinaryIO implementations.
        with pdfplumber.open(source) as document:  # type: ignore[arg-type]
            pages_with_text = [page for page in document.pages if page.chars]
            if not pages_with_text:
                return ExtractionBundle(method="text", requires_ocr=True, evidence=())

            for page in pages_with_text:
                for word in page.extract_words():
                    evidence.append(
                        TextEvidence(
                            page_number=page.page_number,
                            text=str(word["text"]),
                            bbox=BoundingBox(
                                x0=self._coordinate(word["x0"]),
                                top=self._coordinate(word["top"]),
                                x1=self._coordinate(word["x1"]),
                                bottom=self._coordinate(word["bottom"]),
                            ),
                        )
                    )

        return ExtractionBundle(
            method="text", requires_ocr=False, evidence=tuple(evidence)
        )

    @staticmethod
    def _coordinate(value: object) -> float:
        if not isinstance(value, int | float):
            raise TypeError("pdf word coordinate must be numeric")
        return float(value)
