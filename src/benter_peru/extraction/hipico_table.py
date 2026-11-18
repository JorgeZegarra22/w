"""Whitespace-column reconstruction for Jockey Club race programs."""

import json
import re
from collections.abc import Mapping, Sequence

from benter_peru.extraction.models import BoundingBox, StructuredFact, TextEvidence

type Word = Mapping[str, object]


class HipicoTableExtractor:
    """Extract structured runners from the first race using mandil row anchors."""

    _WEIGHT = re.compile(r"^\d{2}\.\d{2}$")

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
        if not horse or not weight or not jockey or not trainer:
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
                "jockey": jockey,
                "trainer": trainer,
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
