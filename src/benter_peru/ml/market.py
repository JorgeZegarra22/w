"""Transparent fair-odds and expected-value calculations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


class MarketError(ValueError):
    """Raised when probabilities or market prices are unsafe."""


@dataclass(frozen=True, slots=True)
class ValueAssessment:
    participant_id: str
    bet_type: Literal["win", "place"]
    estimated_probability: float
    fair_odds: float
    offered_decimal_odds: float
    expected_value: float
    minimum_ev: float
    has_value: bool


def _probability(value: float) -> float:
    probability = float(value)
    if not math.isfinite(probability) or not 0 < probability <= 1:
        raise MarketError("probability must be finite and in (0, 1]")
    return probability


def _odds(value: float) -> float:
    odds = float(value)
    if not math.isfinite(odds) or odds <= 1:
        raise MarketError("offered decimal odds must be finite and greater than one")
    return odds


def fair_odds(probability: float) -> float:
    """Return the no-margin decimal price implied by an estimated probability."""

    return 1.0 / _probability(probability)


def expected_value(probability: float, offered_decimal_odds: float) -> float:
    """Return expected net units per unit staked at total decimal odds."""

    return _probability(probability) * _odds(offered_decimal_odds) - 1.0


def evaluate_market(
    *,
    win_probabilities: Mapping[str, float],
    place_probabilities: Mapping[str, float],
    win_odds: Mapping[str, float] | None = None,
    place_odds: Mapping[str, float] | None = None,
    minimum_ev: float = 0.0,
) -> tuple[ValueAssessment, ...]:
    """Assess only participants with explicitly supplied market prices."""

    if not math.isfinite(minimum_ev):
        raise MarketError("minimum_ev must be finite")
    assessments: list[ValueAssessment] = []
    markets: tuple[
        tuple[Literal["win", "place"], Mapping[str, float], Mapping[str, float]], ...
    ] = (
        ("win", win_probabilities, win_odds or {}),
        ("place", place_probabilities, place_odds or {}),
    )
    for bet_type, probabilities, offered in markets:
        unknown = set(offered) - set(probabilities)
        if unknown:
            raise MarketError(f"unknown participant in {bet_type} odds: {sorted(unknown)[0]}")
        for participant_id in sorted(offered):
            probability = _probability(probabilities[participant_id])
            odds = _odds(offered[participant_id])
            ev = probability * odds - 1.0
            assessments.append(
                ValueAssessment(
                    participant_id=participant_id,
                    bet_type=bet_type,
                    estimated_probability=probability,
                    fair_odds=1.0 / probability,
                    offered_decimal_odds=odds,
                    expected_value=ev,
                    minimum_ev=minimum_ev,
                    has_value=ev > minimum_ev,
                )
            )
    return tuple(assessments)
