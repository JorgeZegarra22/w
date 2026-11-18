"""Deterministic name normalization and conservative fuzzy matching."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Match:
    """A unique fuzzy identity candidate."""

    entity_id: str
    score: float


def normalize_name(value: str) -> str:
    """Return the stable comparison form used by all master entities."""

    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    folded = without_accents.casefold()
    return _NON_ALPHANUMERIC.sub(" ", folded).strip()


def best_match(
    observed_name: str,
    candidates: Mapping[str, str],
    *,
    threshold: float,
) -> Match | None:
    """Return a candidate only when the best score is unique and sufficient."""

    observed = normalize_name(observed_name)
    scored = [
        (
            SequenceMatcher(None, observed, normalize_name(candidate)).ratio(),
            entity_id,
        )
        for entity_id, candidate in candidates.items()
    ]
    eligible = [(score, entity_id) for score, entity_id in scored if score >= threshold]
    if not eligible:
        return None

    eligible.sort(reverse=True)
    best_score, best_id = eligible[0]
    if len(eligible) > 1 and eligible[1][0] == best_score:
        return None
    return Match(entity_id=best_id, score=best_score)
