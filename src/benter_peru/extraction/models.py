"""Typed extraction results shared by adapters and orchestration."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True, slots=True)
class TextEvidence:
    page_number: int
    text: str
    bbox: BoundingBox
    method: Literal["text"] = "text"
    confidence: float = 1.0
    requires_review: bool = False


@dataclass(frozen=True, slots=True)
class ExtractionBundle:
    method: Literal["text"]
    requires_ocr: bool
    evidence: tuple[TextEvidence, ...]
