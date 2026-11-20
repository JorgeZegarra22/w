"""Paired Monte Carlo simulation of hypothetical pace changes."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum, isclose

import numpy as np

from benter_peru.ml.pace import PaceStyle

COLLISION_LEADERS = 3
LEADER_PENALTY = 0.35
CLOSER_BONUS = 0.20
NOISE_SCALE = 0.9


@dataclass(frozen=True, slots=True)
class PaceParticipant:
    participant_id: str
    probability: float
    style: PaceStyle


def count_leaders(participants: Sequence[PaceParticipant]) -> int:
    return sum(item.style == PaceStyle.PUNTERO for item in participants)


def simulate_race(
    participants: Sequence[PaceParticipant], num_simulations: int = 10_000, *, seed: int = 42
) -> dict[str, float]:
    """Transfer baseline mass using the same Gaussian draws with and without pace."""
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
    if count_leaders(participants) >= COLLISION_LEADERS:
        delta = np.asarray(
            [
                -LEADER_PENALTY
                if item.style == PaceStyle.PUNTERO
                else CLOSER_BONUS
                if item.style == PaceStyle.CERRADOR
                else 0.0
                for item in participants
            ]
        )
        # Log-strength plus Gaussian noise supplies the paired counterfactual winners.
        rng = np.random.default_rng(seed)
        energy = np.log(base) + rng.normal(0, NOISE_SCALE, (num_simulations, len(ids)))
        neutral = np.argmax(energy, axis=1)
        tactical = np.argmax(energy + delta, axis=1)
        transitions = np.zeros((len(ids), len(ids)), dtype=np.float64)
        np.add.at(transitions, (neutral, tactical), 1)
        totals = transitions.sum(axis=1)
        for index, total in enumerate(totals):
            if total:
                transitions[index] /= total
            else:
                transitions[index, index] = 1
        adjusted = base @ transitions
    else:
        adjusted = base
    if count_leaders(participants) < COLLISION_LEADERS and sum(base.tolist()) == 1.0:
        return dict(zip(ids, base.tolist(), strict=True))
    total = fsum(adjusted.tolist())
    # Use the largest mass as residual to keep rounding away from near-zero entries.
    residual = int(np.argmax(adjusted))
    result = {name: float(adjusted[i] / total) for i, name in enumerate(ids) if i != residual}
    result[ids[residual]] = 1.0 - sum(result.values())
    return result
