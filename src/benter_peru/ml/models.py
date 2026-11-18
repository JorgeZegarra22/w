"""Synthetic logistic reference model for race-normalized probabilities."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from benter_peru.ml.features import FeatureVector
from benter_peru.ml.probabilities import (
    plackett_luce_place_probabilities,
    stable_softmax,
)

FEATURE_NAMES = (
    "starts_total",
    "wins_total",
    "win_rate",
    "podium_rate",
    "days_since_last_race",
    "distance_starts",
    "distance_wins",
    "distance_win_rate",
    "distance_podium_rate",
    "distance_average_position",
    "surface_starts",
    "surface_wins",
    "surface_win_rate",
    "surface_podium_rate",
    "surface_average_position",
)


class ModelError(ValueError):
    """Raised when model data or configuration is unsafe."""


class ModelNotFittedError(ModelError):
    """Raised when prediction is attempted before fitting."""


@dataclass(frozen=True, slots=True)
class SyntheticTrainingSet:
    features: NDArray[np.float64]
    labels: NDArray[np.int64]
    groups: NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    model_type: str
    training_data: str
    random_state: int
    race_count: int
    field_size: int
    place_positions: int
    production_ready: bool
    calibrated: bool


@dataclass(frozen=True, slots=True)
class RacePrediction:
    win_probabilities: dict[str, float]
    place_probabilities: dict[str, float]
    metadata: ModelMetadata


def encode_feature_vector(features: FeatureVector) -> NDArray[np.float64]:
    """Encode the public FeatureVector in one stable numerical column order."""

    values = [
        features["starts_total"],
        features["wins_total"],
        features["win_rate"],
        features["podium_rate"],
        365.0
        if features["days_since_last_race"] is None
        else features["days_since_last_race"],
        features["distance_starts"],
        features["distance_wins"],
        features["distance_win_rate"],
        features["distance_podium_rate"],
        features["distance_average_position"],
        features["surface_starts"],
        features["surface_wins"],
        features["surface_win_rate"],
        features["surface_podium_rate"],
        features["surface_average_position"],
    ]
    encoded = np.asarray(values, dtype=np.float64)
    if encoded.shape != (len(FEATURE_NAMES),) or not np.isfinite(encoded).all():
        raise ModelError("feature vector must contain finite numerical values")
    return encoded


class SyntheticRaceGenerator:
    """Generate deterministic, internally coherent bootstrap race alternatives."""

    def __init__(self, *, random_state: int = 20261118) -> None:
        self._random_state = random_state

    def generate(
        self, *, race_count: int = 500, field_size: int = 7
    ) -> SyntheticTrainingSet:
        if race_count <= 0:
            raise ModelError("race_count must be positive")
        if field_size < 2:
            raise ModelError("field_size must be at least two")
        rng = np.random.default_rng(self._random_state)
        total_rows = race_count * field_size
        rows = np.empty((total_rows, len(FEATURE_NAMES)), dtype=np.float64)
        labels = np.zeros(total_rows, dtype=np.int64)
        groups = np.repeat(np.arange(race_count, dtype=np.int64), field_size)

        for race_index in range(race_count):
            utilities: list[float] = []
            offset = race_index * field_size
            for participant_index in range(field_size):
                feature_vector = self._participant(rng)
                rows[offset + participant_index] = encode_feature_vector(feature_vector)
                utilities.append(self._latent_utility(feature_vector, rng))
            labels[offset + int(np.argmax(utilities))] = 1
        return SyntheticTrainingSet(features=rows, labels=labels, groups=groups)

    @staticmethod
    def _participant(rng: np.random.Generator) -> FeatureVector:
        starts = int(rng.integers(1, 13))
        wins = int(rng.binomial(starts, rng.uniform(0.05, 0.55)))
        podiums = wins + int(rng.binomial(starts - wins, rng.uniform(0.15, 0.55)))
        distance_starts = int(rng.integers(0, starts + 1))
        distance_wins = min(wins, int(rng.binomial(distance_starts, (wins + 1) / (starts + 2))))
        distance_podiums = min(
            distance_starts,
            distance_wins
            + int(
                rng.binomial(
                    distance_starts - distance_wins,
                    (podiums + 1) / (starts + 2),
                )
            ),
        )
        surface_starts = int(rng.integers(0, starts + 1))
        surface_wins = min(wins, int(rng.binomial(surface_starts, (wins + 1) / (starts + 2))))
        surface_podiums = min(
            surface_starts,
            surface_wins
            + int(
                rng.binomial(
                    surface_starts - surface_wins,
                    (podiums + 1) / (starts + 2),
                )
            ),
        )
        return {
            "starts_total": starts,
            "wins_total": wins,
            "win_rate": wins / starts,
            "podium_rate": podiums / starts,
            "days_since_last_race": (
                None if rng.random() < 0.05 else int(rng.integers(5, 366))
            ),
            "distance_starts": distance_starts,
            "distance_wins": distance_wins,
            "distance_win_rate": distance_wins / distance_starts if distance_starts else 0.0,
            "distance_podium_rate": (
                distance_podiums / distance_starts if distance_starts else 0.0
            ),
            "distance_average_position": (
                float(rng.uniform(1, 7)) if distance_starts else 0.0
            ),
            "surface_starts": surface_starts,
            "surface_wins": surface_wins,
            "surface_win_rate": surface_wins / surface_starts if surface_starts else 0.0,
            "surface_podium_rate": (
                surface_podiums / surface_starts if surface_starts else 0.0
            ),
            "surface_average_position": (
                float(rng.uniform(1, 7)) if surface_starts else 0.0
            ),
        }

    @staticmethod
    def _latent_utility(features: FeatureVector, rng: np.random.Generator) -> float:
        recency = features["days_since_last_race"]
        days = 365 if recency is None else recency
        return float(
            3.0 * features["win_rate"]
            + 2.0 * features["podium_rate"]
            + 2.0 * features["distance_win_rate"]
            + 1.2 * features["distance_podium_rate"]
            + 1.5 * features["surface_win_rate"]
            + 0.8 * features["surface_podium_rate"]
            - 0.2 * features["distance_average_position"]
            - 0.1 * features["surface_average_position"]
            - 0.002 * days
            + rng.gumbel(0.0, 0.8)
        )


class BaselineRaceModel:
    """Participant logit utilities normalized jointly within each target race."""

    def __init__(
        self,
        *,
        place_positions: int = 3,
        random_state: int = 20261118,
    ) -> None:
        if place_positions <= 0:
            raise ModelError("place_positions must be positive")
        self._place_positions = place_positions
        self._random_state = random_state
        self._pipeline: Pipeline | None = None
        self._metadata: ModelMetadata | None = None

    @property
    def pipeline(self) -> Pipeline:
        if self._pipeline is None:
            raise ModelNotFittedError("model must be fitted before accessing its pipeline")
        return self._pipeline

    def fit_synthetic(
        self, *, race_count: int = 500, field_size: int = 7
    ) -> BaselineRaceModel:
        training = SyntheticRaceGenerator(random_state=self._random_state).generate(
            race_count=race_count, field_size=field_size
        )
        pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "logistic",
                    LogisticRegression(
                        solver="lbfgs",
                        max_iter=1000,
                        random_state=self._random_state,
                    ),
                ),
            ]
        )
        pipeline.fit(training.features, training.labels)
        self._pipeline = pipeline
        self._metadata = ModelMetadata(
            model_type="synthetic_softmax_baseline",
            training_data="synthetic",
            random_state=self._random_state,
            race_count=race_count,
            field_size=field_size,
            place_positions=self._place_positions,
            production_ready=False,
            calibrated=False,
        )
        return self

    def predict_race(
        self, participants: Mapping[str, FeatureVector]
    ) -> RacePrediction:
        if self._pipeline is None or self._metadata is None:
            raise ModelNotFittedError("model must be fitted before prediction")
        if len(participants) < 2:
            raise ModelError("at least two participants are required")
        if self._place_positions > len(participants):
            raise ModelError("place_positions cannot exceed participant count")
        if any(not participant_id for participant_id in participants):
            raise ModelError("participant IDs must be non-empty")
        participant_ids = tuple(participants)
        matrix = np.vstack(
            [
                encode_feature_vector(participants[participant_id])
                for participant_id in participant_ids
            ]
        )
        decision = np.asarray(self._pipeline.decision_function(matrix), dtype=np.float64)
        utilities = {
            participant_id: float(value)
            for participant_id, value in zip(participant_ids, decision, strict=True)
        }
        if any(not math.isfinite(value) for value in utilities.values()):
            raise ModelError("model produced non-finite utilities")
        wins = stable_softmax(utilities)
        places = plackett_luce_place_probabilities(wins, self._place_positions)
        return RacePrediction(
            win_probabilities=wins,
            place_probabilities=places,
            metadata=self._metadata,
        )
