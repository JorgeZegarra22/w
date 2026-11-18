"""Stable softmax and exact Plackett-Luce place probabilities."""

from __future__ import annotations

import math
from collections.abc import Mapping

_TOLERANCE = 1e-12


class ProbabilityError(ValueError):
    """Raised when a probability distribution cannot be formed safely."""


def _validated_values(values: Mapping[str, float], *, positive: bool) -> list[tuple[str, float]]:
    items = [(participant_id, float(value)) for participant_id, value in values.items()]
    if len(items) < 2:
        raise ProbabilityError("at least two participants are required")
    for participant_id, value in items:
        if not participant_id:
            raise ProbabilityError("participant IDs must be non-empty")
        if not math.isfinite(value):
            raise ProbabilityError("values must be finite")
        if positive and value <= 0:
            raise ProbabilityError("strengths must be positive")
    return items


def stable_softmax(utilities: Mapping[str, float]) -> dict[str, float]:
    """Normalize participant utilities and force an exact floating-point sum of one."""

    items = _validated_values(utilities, positive=False)
    maximum = max(value for _, value in items)
    exponentials = [math.exp(value - maximum) for _, value in items]
    total = sum(exponentials)
    if not math.isfinite(total) or total <= 0:
        raise ProbabilityError("softmax total must be positive and finite")

    probabilities: dict[str, float] = {}
    for (participant_id, _), exponential in zip(items[:-1], exponentials[:-1], strict=True):
        probabilities[participant_id] = exponential / total
    final_id = items[-1][0]
    probabilities[final_id] = 1.0 - sum(probabilities.values())
    if any(not math.isfinite(value) or value <= 0 or value > 1 for value in probabilities.values()):
        raise ProbabilityError("softmax produced an invalid probability")
    if sum(probabilities.values()) != 1.0:
        raise ProbabilityError("softmax probabilities do not sum exactly to one")
    return probabilities


def plackett_luce_place_probabilities(
    strengths: Mapping[str, float], place_positions: int
) -> dict[str, float]:
    """Return exact inclusion probabilities for the first N ordered positions."""

    items = _validated_values(strengths, positive=True)
    if not 1 <= place_positions <= len(items):
        raise ProbabilityError("place_positions must be between one and field size")
    total = sum(value for _, value in items)
    if not math.isfinite(total) or total <= 0:
        raise ProbabilityError("strength total must be positive and finite")
    normalized = tuple((participant_id, value / total) for participant_id, value in items)
    result = {participant_id: 0.0 for participant_id, _ in normalized}

    def enumerate_orders(
        remaining: tuple[tuple[str, float], ...],
        selected: tuple[str, ...],
        branch_probability: float,
    ) -> None:
        if len(selected) == place_positions:
            for participant_id in selected:
                result[participant_id] += branch_probability
            return
        remaining_total = sum(value for _, value in remaining)
        for index, (participant_id, value) in enumerate(remaining):
            enumerate_orders(
                remaining[:index] + remaining[index + 1 :],
                (*selected, participant_id),
                branch_probability * value / remaining_total,
            )

    enumerate_orders(normalized, (), 1.0)
    if any(
        not math.isfinite(value) or value < -_TOLERANCE or value > 1 + _TOLERANCE
        for value in result.values()
    ):
        raise ProbabilityError("Plackett-Luce produced an invalid probability")
    if not math.isclose(sum(result.values()), place_positions, abs_tol=_TOLERANCE):
        raise ProbabilityError("place probabilities do not conserve the available places")
    return result
