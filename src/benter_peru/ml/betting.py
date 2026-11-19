"""Pure, fail-closed betting mathematics for explicit market prices."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import permutations
from typing import Literal


class BettingError(ValueError):
    """Raised when a betting input cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class OrderedCombination:
    bet_type: Literal["exacta", "trifecta"]
    participant_ids: tuple[str, ...]
    joint_probability: float
    fair_odds: float


def _probability(value: float) -> float:
    probability = float(value)
    if not math.isfinite(probability) or not 0 < probability <= 1:
        raise BettingError("probability must be finite and in (0, 1]")
    return probability


def _decimal_odds(value: float) -> float:
    odds = float(value)
    if not math.isfinite(odds) or odds <= 1:
        raise BettingError("offered odds must be finite and greater than one")
    return odds


def calculate_expected_value(probability: float, offered_odds: float) -> float:
    """Return expected net units per unit staked at total decimal odds."""
    return _probability(probability) * _decimal_odds(offered_odds) - 1.0


def calculate_kelly_stake(
    probability: float,
    offered_odds: float,
    fraction: float = 0.25,
) -> float:
    """Return a conservative fractional-Kelly share of total bankroll."""
    p = _probability(probability)
    odds = _decimal_odds(offered_odds)
    multiplier = float(fraction)
    if not math.isfinite(multiplier) or not 0 < multiplier <= 1:
        raise BettingError("fraction must be finite and in (0, 1]")
    expected_value = p * odds - 1.0
    if expected_value <= 0:
        return 0.0
    net_odds = odds - 1.0
    full_kelly = (net_odds * p - (1.0 - p)) / net_odds
    return max(0.0, multiplier * full_kelly)


def generate_top_combinations(
    race_probabilities: Mapping[str, float],
    bet_type: Literal["exacta", "trifecta"] = "exacta",
    top_n: int = 3,
) -> tuple[OrderedCombination, ...]:
    """Return the strongest ordered finishes under exact Plackett-Luce."""
    if bet_type not in {"exacta", "trifecta"}:
        raise BettingError("bet_type must be exacta or trifecta")
    if top_n <= 0:
        raise BettingError("top_n must be positive")
    positions = 2 if bet_type == "exacta" else 3
    if len(race_probabilities) < positions:
        raise BettingError(f"{bet_type} requires at least {positions} participants")
    strengths: dict[str, float] = {}
    for participant_id, raw_strength in race_probabilities.items():
        strength = float(raw_strength)
        if not participant_id:
            raise BettingError("participant IDs must be non-empty")
        if not math.isfinite(strength) or strength <= 0:
            raise BettingError("race probabilities must be finite and positive")
        strengths[participant_id] = strength
    total = sum(strengths.values())
    if not math.isfinite(total) or total <= 0:
        raise BettingError("race probability total must be finite and positive")

    combinations: list[OrderedCombination] = []
    for ordered_ids in permutations(sorted(strengths), positions):
        remaining_total = total
        joint_probability = 1.0
        for participant_id in ordered_ids:
            strength = strengths[participant_id]
            joint_probability *= strength / remaining_total
            remaining_total -= strength
        combinations.append(
            OrderedCombination(
                bet_type=bet_type,
                participant_ids=ordered_ids,
                joint_probability=joint_probability,
                fair_odds=1.0 / joint_probability,
            )
        )
    combinations.sort(
        key=lambda item: (-item.joint_probability, item.participant_ids)
    )
    return tuple(combinations[:top_n])
