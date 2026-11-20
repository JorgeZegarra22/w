"""Classify running style using observed tactical evidence only."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from benter_peru.entities.normalization import normalize_name


class PaceStyle(StrEnum):
    PUNTERO = "PUNTERO"
    CERRADOR = "CERRADOR"
    MEDIO = "MEDIO"


@dataclass(frozen=True, slots=True)
class PaceAssessment:
    style: PaceStyle
    evidence: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.style.value.capitalize() if self.evidence else "Medio · sin evidencia"


def _position(value: object) -> int | None:
    match = re.fullmatch(r"\s*([1-9]\d*)[º°ª]?(?:\s*/\s*[1-9]\d*)?\s*", str(value))
    return int(match[1]) if match else None


def classify_pace(profile: Mapping[str, object]) -> PaceAssessment:
    history = profile.get("recent_races")
    if not isinstance(history, list):
        return PaceAssessment(PaceStyle.MEDIO)
    leaders: list[str] = []
    closers: list[str] = []
    for row in history:
        if not isinstance(row, Mapping):
            continue
        comment = normalize_name(str(row.get("comments", "")))
        cue = next(
            (
                match
                for match in ("de punta a punta", "peleo la punta")
                if re.search(rf"\b{match}\b", comment)
            ),
            None,
        )
        if cue:
            leaders.append(cue)
            continue
        early = _position(row.get("initial_position")) or _position(row.get("early_position"))
        splits = row.get("sectionals")
        if early is None and isinstance(splits, list) and splits and isinstance(splits[0], Mapping):
            early = _position(splits[0].get("position"))
        finish = _position(row.get("position"))
        if early is not None and early <= 2:
            leaders.append(f"posición inicial {early}")
        elif (
            early is not None
            and finish is not None
            and early >= 5
            and finish <= 3
            and early - finish >= 3
        ):
            closers.append(f"{early}º al inicio, {finish}º al final")
    if len(leaders) > len(closers):
        return PaceAssessment(PaceStyle.PUNTERO, tuple(leaders))
    if len(closers) > len(leaders):
        return PaceAssessment(PaceStyle.CERRADOR, tuple(closers))
    return PaceAssessment(PaceStyle.MEDIO, tuple(leaders + closers))
