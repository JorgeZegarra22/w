"""Paired Monte Carlo simulation of hypothetical pace changes."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum, isclose, isfinite

import numpy as np

from benter_peru.ml.pace import PaceStyle

COLLISION_LEADERS = 3
LEADER_PENALTY = 0.35
CLOSER_BONUS = 0.20
NOISE_SCALE = 0.9
FINAL_STRETCH_METERS = 400
FINAL_STRETCH_ENERGY = {"fatiga alta": -0.55, "resistencia alta": 0.25}
MAX_STRIDE_MODULATION = 0.30


@dataclass(frozen=True, slots=True)
class PaceParticipant:
    participant_id: str
    probability: float
    style: PaceStyle
    fatigue_factor: str | None = None
    stride_drop_pct: float | None = None

    def final_stretch_energy(self) -> float:
        """Apply a heuristic log-strength change at the end of the race."""
        if self.stride_drop_pct is not None and not isfinite(self.stride_drop_pct):
            raise ValueError("La variación de zancada debe ser finita.")
        factor = " ".join((self.fatigue_factor or "").lower().split())
        stride_change = min(abs(self.stride_drop_pct or 0.0) / 100, MAX_STRIDE_MODULATION)
        return FINAL_STRETCH_ENERGY.get(factor, 0.0) * (1 + stride_change)


def count_leaders(participants: Sequence[PaceParticipant]) -> int:
    return sum(item.style == PaceStyle.PUNTERO for item in participants)


def simulate_race(
    participants: Sequence[PaceParticipant],
    num_simulations: int = 10_000,
    *,
    seed: int = 42,
    include_biomechanics: bool = True,
) -> dict[str, float]:
    """Transfer baseline mass using shared Gaussian draws across scenarios."""
    if len(participants) < 2 or num_simulations < 1:
        raise ValueError("Se requieren dos participantes y al menos una simulación.")
    ids = tuple(item.participant_id for item in participants)
    base = np.asarray([item.probability for item in participants], dtype=np.float64)
    if (
        len(set(ids)) != len(ids)
        or not all(ids)
        or not np.isfinite(base).all()
        or np.any(base <= 0)
        or not isclose(float(base.sum()), 1.0, abs_tol=1e-9)
    ):
        raise ValueError("Los participantes deben tener IDs únicos y probabilidades que sumen 1.")
    collision = count_leaders(participants) >= COLLISION_LEADERS
    delta = np.zeros(len(ids), dtype=np.float64)
    if collision:
        for index, item in enumerate(participants):
            if item.style == PaceStyle.PUNTERO:
                delta[index] = -LEADER_PENALTY
            elif item.style == PaceStyle.CERRADOR:
                delta[index] = CLOSER_BONUS
    # Log-strength plus Gaussian noise supplies the paired counterfactual winners.
    rng = np.random.default_rng(seed)
    energy = np.log(base) + rng.normal(0, NOISE_SCALE, (num_simulations, len(ids)))
    neutral = np.argmax(energy, axis=1)
    final_energy = energy + delta
    if include_biomechanics:
        final_energy += np.asarray([item.final_stretch_energy() for item in participants])
    tactical = np.argmax(final_energy, axis=1)
    if np.array_equal(neutral, tactical) and sum(base.tolist()) == 1.0:
        return dict(zip(ids, base.tolist(), strict=True))
    transitions = np.zeros((len(ids), len(ids)), dtype=np.float64)
    np.add.at(transitions, (neutral, tactical), 1)
    totals = transitions.sum(axis=1)
    for index, total in enumerate(totals):
        if total:
            transitions[index] /= total
        else:
            transitions[index, index] = 1
    adjusted = base @ transitions
    total = fsum(adjusted.tolist())
    # Use the largest mass as residual to keep rounding away from near-zero entries.
    residual = int(np.argmax(adjusted))
    result = {name: float(adjusted[i] / total) for i, name in enumerate(ids) if i != residual}
    result[ids[residual]] = 1.0 - sum(result.values())
    return result
