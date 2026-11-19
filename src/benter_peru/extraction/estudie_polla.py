"""Deterministic text-layer extraction for “Estudie su Polla” selections."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO

import pdfplumber

from benter_peru.extraction.models import (
    BoundingBox,
    ExtractionBundle,
    StructuredFact,
    TextEvidence,
)

type PdfSource = str | Path | BinaryIO
type Word = Mapping[str, object]


class EstudiePollaExtractionError(ValueError):
    """Raised when an identified magazine cannot be parsed safely."""


class EstudiePollaExtractor:
    _MEETING = re.compile(r"REUNI[OÓ]N\s+(\d{6})", re.IGNORECASE)
    _ROW = re.compile(r"^(\d{1,2})\s*\|\s*([^|]+?)\s*\|\s*(.+)$")
    _NUMBERED_PICK = re.compile(r"^\s*(\d{1,2})\s+(.+?)\s*$")

    def extract(self, source: PdfSource) -> ExtractionBundle:
        facts: list[StructuredFact] = []
        evidence: list[TextEvidence] = []
        with pdfplumber.open(source) as document:  # type: ignore[arg-type]
            if not any(page.chars for page in document.pages):
                return ExtractionBundle(method="text", requires_ocr=True, evidence=())
            all_text = "\n".join(page.extract_text() or "" for page in document.pages)
            meeting_match = self._MEETING.search(all_text)
            if meeting_match is None or re.search(
                r"PRON[OÓ]STICO", all_text, re.IGNORECASE
            ) is None:
                raise EstudiePollaExtractionError("magazine markers are missing")
            meeting_code = meeting_match[1]
            for page in document.pages:
                for line_words in self._lines(page.extract_words()):
                    line_text = " ".join(str(word["text"]) for word in line_words)
                    row_match = self._ROW.fullmatch(line_text)
                    if row_match is None:
                        continue
                    race_number = int(row_match[1])
                    journalist = row_match[2].strip()
                    selections = [item.strip() for item in row_match[3].split(",")]
                    row_evidence = self._evidence(page.page_number, line_text, line_words)
                    evidence.append(row_evidence)
                    for rank, selection in enumerate(selections, start=1):
                        numbered = self._NUMBERED_PICK.fullmatch(selection)
                        mandil = int(numbered[1]) if numbered else None
                        horse_name = (numbered[2] if numbered else selection).strip()
                        requires_review = numbered is None
                        confidence = 0.55 if requires_review else 0.97
                        payload = {
                            "meeting_code": meeting_code,
                            "race_number": race_number,
                            "rank": rank,
                            "mandil": mandil,
                            "horse_name": horse_name,
                            "journalist": journalist,
                        }
                        facts.append(
                            StructuredFact(
                                fact_type="journalist_pick",
                                subject_key=(
                                    f"meeting:{meeting_code}:race:{race_number}:pick:{rank}"
                                ),
                                normalized_value=json.dumps(
                                    payload, ensure_ascii=False, sort_keys=True
                                ),
                                raw_value=selection,
                                confidence=confidence,
                                requires_review=requires_review,
                                evidence=TextEvidence(
                                    page_number=row_evidence.page_number,
                                    text=row_evidence.text,
                                    bbox=row_evidence.bbox,
                                    confidence=confidence,
                                    requires_review=requires_review,
                                ),
                            )
                        )
        if not facts:
            raise EstudiePollaExtractionError("no parseable selection rows")
        return ExtractionBundle(
            method="text",
            requires_ocr=False,
            evidence=tuple(evidence),
            facts=tuple(facts),
        )

    @staticmethod
    def _lines(words: Sequence[Word]) -> tuple[tuple[Word, ...], ...]:
        groups: list[list[Word]] = []
        for word in sorted(
            words,
            key=lambda item: (
                EstudiePollaExtractor._number(item, "top"),
                EstudiePollaExtractor._number(item, "x0"),
            ),
        ):
            if not groups or abs(
                EstudiePollaExtractor._number(groups[-1][0], "top")
                - EstudiePollaExtractor._number(word, "top")
            ) > 3:
                groups.append([word])
            else:
                groups[-1].append(word)
        return tuple(tuple(group) for group in groups)

    @staticmethod
    def _evidence(page_number: int, text: str, words: Sequence[Word]) -> TextEvidence:
        return TextEvidence(
            page_number=page_number,
            text=text,
            bbox=BoundingBox(
                x0=min(EstudiePollaExtractor._number(word, "x0") for word in words),
                top=min(EstudiePollaExtractor._number(word, "top") for word in words),
                x1=max(EstudiePollaExtractor._number(word, "x1") for word in words),
                bottom=max(
                    EstudiePollaExtractor._number(word, "bottom") for word in words
                ),
            ),
        )

    @staticmethod
    def _number(word: Word, key: str) -> float:
        value = word[key]
        if not isinstance(value, int | float):
            raise EstudiePollaExtractionError(f"invalid PDF coordinate: {key}")
        return float(value)
