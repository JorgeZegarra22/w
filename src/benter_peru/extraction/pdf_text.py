"""Text-layer PDF extraction using pdfplumber word coordinates."""

from pathlib import Path
from typing import BinaryIO

import pdfplumber

from benter_peru.extraction.hipico_table import HipicoTableExtractor
from benter_peru.extraction.models import (
    BoundingBox,
    ExtractionBundle,
    StructuredFact,
    TextEvidence,
)

type PdfSource = str | Path | BinaryIO


class TextPdfExtractor:
    """Extract word evidence from machine-generated PDFs without OCR."""

    def __init__(self, table_extractor: HipicoTableExtractor | None = None) -> None:
        self._table_extractor = table_extractor or HipicoTableExtractor()

    def extract(self, source: PdfSource) -> ExtractionBundle:
        evidence: list[TextEvidence] = []
        structured_facts: list[StructuredFact] = []
        # pdfplumber accepts seekable binary streams at runtime, while its public
        # type annotation enumerates only a subset of BinaryIO implementations.
        with pdfplumber.open(source) as document:  # type: ignore[arg-type]
            pages_with_text = [page for page in document.pages if page.chars]
            if not pages_with_text:
                return ExtractionBundle(method="text", requires_ocr=True, evidence=())

            page_words = [(page, page.extract_words()) for page in pages_with_text]
            document_header_words = page_words[0][1]
            for page, words in page_words:
                structured_facts.extend(
                    self._table_extractor.extract(
                        words,
                        page_number=page.page_number,
                        page_width=float(page.width),
                        document_header_words=document_header_words,
                    )
                )
                for word in words:
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
            method="text",
            requires_ocr=False,
            evidence=tuple(evidence),
            facts=tuple(structured_facts),
        )

    @staticmethod
    def _coordinate(value: object) -> float:
        if not isinstance(value, int | float):
            raise TypeError("pdf word coordinate must be numeric")
        return float(value)
