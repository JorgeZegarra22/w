"""Whitespace-column reconstruction for Jockey Club race programs."""

import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import ClassVar

from benter_peru.extraction.models import BoundingBox, StructuredFact, TextEvidence

type Word = Mapping[str, object]


class HipicoTableExtractor:
    """Extract structured runners from the first race using mandil row anchors."""

    _WEIGHT = re.compile(r"^\d{2}\.\d{2}$")
    _MONTHS: ClassVar[dict[str, int]] = {
        "ENERO": 1,
        "FEBRERO": 2,
        "MARZO": 3,
        "ABRIL": 4,
        "MAYO": 5,
        "JUNIO": 6,
        "JULIO": 7,
        "AGOSTO": 8,
        "SEPTIEMBRE": 9,
        "OCTUBRE": 10,
        "NOVIEMBRE": 11,
        "DICIEMBRE": 12,
    }

    def extract(
        self,
        words: Sequence[Word],
        *,
        page_number: int,
        page_width: float,
    ) -> tuple[StructuredFact, ...]:
        first_header = self._header_top(words, "1ra")
        second_header = self._header_top(words, "2da")
        if first_header is None or second_header is None or second_header <= first_header:
            return ()

        anchors = sorted(
            (
                word
                for word in words
                if self._text(word).isdigit()
                and self._x0(word) < page_width * 0.09
                and first_header + 8 < self._top(word) < second_header
            ),
            key=self._center_y,
        )
        if not anchors:
            return ()

        facts: list[StructuredFact] = []
        context = self._context_fact(
            words,
            page_number=page_number,
            first_header=first_header,
        )
        if context is not None:
            facts.append(context)
        centers = [self._center_y(anchor) for anchor in anchors]
        for index, anchor in enumerate(anchors):
            lower = (
                (centers[index - 1] + centers[index]) / 2
                if index > 0
                else centers[index] - self._first_half_gap(centers)
            )
            upper = (
                (centers[index] + centers[index + 1]) / 2
                if index + 1 < len(centers)
                else centers[index] + self._last_half_gap(centers)
            )
            row_words = [
                word
                for word in words
                if lower <= self._center_y(word) < upper
                and self._x0(word) < page_width * 0.80
            ]
            fact = self._row_fact(
                row_words,
                mandil=int(self._text(anchor)),
                page_number=page_number,
                page_width=page_width,
            )
            if fact is not None:
                facts.append(fact)
        return tuple(facts)

    def _row_fact(
        self,
        words: Sequence[Word],
        *,
        mandil: int,
        page_number: int,
        page_width: float,
    ) -> StructuredFact | None:
        horse = self._join_band(words, page_width * 0.09, page_width * 0.285)
        weight_words = self._words_in_band(words, page_width * 0.285, page_width * 0.38)
        weight = next(
            (self._text(word) for word in weight_words if self._WEIGHT.fullmatch(self._text(word))),
            "",
        )
        jockey = self._join_band(words, page_width * 0.56, page_width * 0.67)
        trainer = self._join_band(words, page_width * 0.67, page_width * 0.80)
        stud = self._join_band(words, page_width * 0.435, page_width * 0.56)
        if not horse or not weight or not stud or not jockey or not trainer:
            return None

        ordered = sorted(words, key=lambda word: (self._x0(word), self._top(word)))
        raw_value = " ".join(self._text(word) for word in ordered)
        noisy = self._is_noisy_horse_name(horse)
        confidence = 0.55 if noisy else 0.95
        bbox = BoundingBox(
            x0=min(self._x0(word) for word in words),
            top=min(self._top(word) for word in words),
            x1=max(self._x1(word) for word in words),
            bottom=max(self._bottom(word) for word in words),
        )
        evidence = TextEvidence(
            page_number=page_number,
            text=raw_value,
            bbox=bbox,
            confidence=confidence,
            requires_review=noisy,
        )
        normalized = json.dumps(
            {
                "mandil": mandil,
                "horse_name": horse,
                "weight": weight,
                "stud": stud,
                "jockey": jockey,
                "trainer": trainer,
                "horse_requires_review": noisy,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return StructuredFact(
            fact_type="race_entry",
            subject_key=f"race:1:mandil:{mandil}",
            normalized_value=normalized,
            raw_value=raw_value,
            confidence=confidence,
            requires_review=noisy,
            evidence=evidence,
        )

    def _context_fact(
        self,
        words: Sequence[Word],
        *,
        page_number: int,
        first_header: float,
    ) -> StructuredFact | None:
        ordered = sorted(words, key=lambda word: (self._top(word), self._x0(word)))
        full_text = " ".join(self._text(word) for word in ordered)
        meeting_match = re.search(r"REUN.{0,12}?(\d{6})", full_text, re.IGNORECASE)
        scheduled = self._header_date(words, first_header)
        header_words = [
            word for word in words if first_header - 2 <= self._top(word) <= first_header + 8
        ]
        header_text = " ".join(
            self._text(word) for word in sorted(header_words, key=self._x0)
        )
        distance_match = re.search(
            r"DISTANCIA\s+([\d,.]+)\s+METROS", header_text, re.IGNORECASE
        )
        surface_match = re.search(r"\b(ARENA|CESPED)\b", header_text, re.IGNORECASE)
        if not meeting_match or scheduled is None or not distance_match or not surface_match:
            return None
        distance = int(re.sub(r"\D", "", distance_match[1]))
        meeting_code = meeting_match[1]
        context_words = [word for word in words if self._top(word) <= first_header + 8]
        bbox = BoundingBox(
            x0=min(self._x0(word) for word in context_words),
            top=min(self._top(word) for word in context_words),
            x1=max(self._x1(word) for word in context_words),
            bottom=max(self._bottom(word) for word in context_words),
        )
        raw_value = " ".join(
            self._text(word)
            for word in sorted(context_words, key=lambda word: (self._top(word), self._x0(word)))
        )
        normalized = json.dumps(
            {
                "meeting_code": meeting_code,
                "race_number": 1,
                "scheduled_date": scheduled.isoformat(),
                "distance_meters": distance,
                "surface": surface_match[1].lower(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        evidence = TextEvidence(
            page_number=page_number,
            text=raw_value,
            bbox=bbox,
            confidence=0.95,
            requires_review=False,
        )
        return StructuredFact(
            fact_type="race_context",
            subject_key=f"meeting:{meeting_code}:race:1",
            normalized_value=normalized,
            raw_value=raw_value,
            confidence=0.95,
            requires_review=False,
            evidence=evidence,
        )

    @classmethod
    def _header_date(cls, words: Sequence[Word], first_header: float) -> date | None:
        """Recover the printed date despite small baseline offsets between words."""

        candidates = [word for word in words if cls._top(word) < first_header]
        month_word = next(
            (
                word
                for word in candidates
                if cls._text(word).upper() in cls._MONTHS
            ),
            None,
        )
        if month_word is None:
            return None
        month_top = cls._top(month_word)
        same_line = [
            word for word in candidates if abs(cls._top(word) - month_top) <= 3.0
        ]
        day_word = next(
            (
                word
                for word in same_line
                if cls._x0(word) < cls._x0(month_word)
                and cls._text(word).isdigit()
                and 1 <= int(cls._text(word)) <= 31
            ),
            None,
        )
        year_word = next(
            (
                word
                for word in same_line
                if cls._x0(word) > cls._x0(month_word)
                and cls._text(word).isdigit()
                and 2000 <= int(cls._text(word)) <= 2100
            ),
            None,
        )
        if day_word is None or year_word is None:
            return None
        return date(
            int(cls._text(year_word)),
            cls._MONTHS[cls._text(month_word).upper()],
            int(cls._text(day_word)),
        )

    @classmethod
    def _header_top(cls, words: Sequence[Word], prefix: str) -> float | None:
        return next(
            (
                cls._top(word)
                for word in sorted(words, key=cls._top)
                if cls._text(word).casefold().startswith(prefix)
            ),
            None,
        )

    @classmethod
    def _join_band(cls, words: Sequence[Word], lower: float, upper: float) -> str:
        return " ".join(
            cls._text(word)
            for word in sorted(cls._words_in_band(words, lower, upper), key=cls._x0)
        )

    @classmethod
    def _words_in_band(
        cls, words: Sequence[Word], lower: float, upper: float
    ) -> list[Word]:
        return [word for word in words if lower <= cls._x0(word) < upper]

    @staticmethod
    def _is_noisy_horse_name(value: str) -> bool:
        return any(character.islower() for character in value) or "�" in value

    @staticmethod
    def _first_half_gap(centers: Sequence[float]) -> float:
        return (centers[1] - centers[0]) / 2 if len(centers) > 1 else 8.0

    @staticmethod
    def _last_half_gap(centers: Sequence[float]) -> float:
        return (centers[-1] - centers[-2]) / 2 if len(centers) > 1 else 8.0

    @staticmethod
    def _text(word: Word) -> str:
        return str(word["text"])

    @staticmethod
    def _coordinate(word: Word, name: str) -> float:
        value = word[name]
        if not isinstance(value, int | float):
            raise TypeError(f"word {name} must be numeric")
        return float(value)

    @classmethod
    def _x0(cls, word: Word) -> float:
        return cls._coordinate(word, "x0")

    @classmethod
    def _x1(cls, word: Word) -> float:
        return cls._coordinate(word, "x1")

    @classmethod
    def _top(cls, word: Word) -> float:
        return cls._coordinate(word, "top")

    @classmethod
    def _bottom(cls, word: Word) -> float:
        return cls._coordinate(word, "bottom")

    @classmethod
    def _center_y(cls, word: Word) -> float:
        return (cls._top(word) + cls._bottom(word)) / 2
