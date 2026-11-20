"""Synthetic logistic reference model for race-normalized probabilities."""

from __future__ import annotations

import math
import pickle
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from hmac import compare_digest
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol, cast

import lightgbm
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from benter_peru.ml.ensemble import MODEL_WEIGHTS, EnsembleEstimator, normalize_race_scores
from benter_peru.ml.features import FeatureVector
from benter_peru.ml.probabilities import (
    plackett_luce_place_probabilities,
    stable_softmax,
)
from benter_peru.ml.real_features import (
    CATEGORICAL_FEATURE_COLUMNS,
    LIGHTGBM_FEATURE_COLUMNS,
    HistoricalFeatureError,
    HistoricalLightGBMFeatureEngine,
    RealRaceParticipant,
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


class RealModelArtifactError(ModelError):
    """Raised when a trusted real-model artifact cannot be used safely."""


class _ProbabilityEstimator(Protocol):
    @property
    def n_features_in_(self) -> int: ...

    def predict_proba(self, values: pd.DataFrame) -> object: ...


@dataclass(frozen=True, slots=True)
class RealModelMetadata:
    model_type: str
    training_rows: int
    training_start: date
    training_end: date
    artifact_sha256: str
    production_ready: bool = False
    calibrated: bool = False


@dataclass(frozen=True, slots=True)
class RealRacePrediction:
    win_probabilities: dict[str, float]
    place_probabilities: dict[str, float]
    fair_odds: dict[str, float]
    metadata: RealModelMetadata
    distance_meters: int
    surface: str


class RealLightGBMRaceModel:
    """Hash-pinned LightGBM inference over leakage-safe historical features."""

    def __init__(
        self,
        *,
        estimator: _ProbabilityEstimator,
        feature_engine: HistoricalLightGBMFeatureEngine,
        global_win_rate: float | None,
        artifact_sha256: str,
        place_positions: int,
    ) -> None:
        self._estimator = estimator
        self._feature_engine = feature_engine
        self._global_win_rate = global_win_rate
        self._artifact_sha256 = artifact_sha256
        self._place_positions = place_positions

    @classmethod
    def load(
        cls,
        *,
        model_path: Path,
        dataset_path: Path,
        expected_sha256: str,
        place_positions: int = 3,
    ) -> RealLightGBMRaceModel:
        if not model_path.is_file():
            raise RealModelArtifactError(f"model artifact not found: {model_path}")
        if not dataset_path.is_file():
            raise RealModelArtifactError(f"historical dataset not found: {dataset_path}")
        if place_positions <= 0:
            raise RealModelArtifactError("place_positions must be positive")
        digest = sha256(model_path.read_bytes()).hexdigest()
        if not compare_digest(digest, expected_sha256.casefold()):
            raise RealModelArtifactError("model artifact SHA-256 mismatch")
        if lightgbm.__version__.split(".", 1)[0] != "4":
            raise RealModelArtifactError("incompatible LightGBM major version")
        try:
            with model_path.open("rb") as stream:
                # The digest is verified before this executable format is loaded.
                loaded: Any = pickle.load(stream)
        except Exception as error:
            raise RealModelArtifactError("model artifact could not be deserialized") from error
        if not isinstance(loaded, Mapping):
            raise RealModelArtifactError("model artifact must be a mapping")
        required = {"model", "feature_cols", "categorical_cols", "global_win_rate"}
        if not required.issubset(loaded):
            raise RealModelArtifactError("model artifact is missing required keys")
        feature_columns = tuple(str(value) for value in loaded["feature_cols"])
        categorical_columns = tuple(str(value) for value in loaded["categorical_cols"])
        if feature_columns != LIGHTGBM_FEATURE_COLUMNS:
            raise RealModelArtifactError("model feature column contract is incompatible")
        if categorical_columns != CATEGORICAL_FEATURE_COLUMNS:
            raise RealModelArtifactError("model categorical column contract is incompatible")
        estimator_object = loaded["model"]
        if not hasattr(estimator_object, "predict_proba") or getattr(
            estimator_object, "n_features_in_", None
        ) != len(LIGHTGBM_FEATURE_COLUMNS):
            raise RealModelArtifactError("model estimator contract is incompatible")
        try:
            global_win_rate = float(loaded["global_win_rate"])
        except (TypeError, ValueError) as error:
            raise RealModelArtifactError("model global win rate is invalid") from error
        if not math.isfinite(global_win_rate) or not 0 <= global_win_rate <= 1:
            raise RealModelArtifactError("model global win rate is invalid")
        try:
            feature_engine = HistoricalLightGBMFeatureEngine(dataset_path)
        except HistoricalFeatureError as error:
            raise RealModelArtifactError(str(error)) from error
        return cls(
            estimator=cast(_ProbabilityEstimator, estimator_object),
            feature_engine=feature_engine,
            global_win_rate=global_win_rate,
            artifact_sha256=digest,
            place_positions=place_positions,
        )

    @property
    def metadata(self) -> RealModelMetadata:
        training_start, training_end = self._feature_engine.date_range
        return RealModelMetadata(
            model_type="historical_lightgbm_v1",
            training_rows=self._feature_engine.row_count,
            training_start=training_start,
            training_end=training_end,
            artifact_sha256=self._artifact_sha256,
        )

    def predict_race(
        self,
        *,
        race_date: date,
        distance_meters: int,
        surface: str,
        participants: tuple[RealRaceParticipant, ...],
    ) -> RealRacePrediction:
        if len(participants) < 2:
            raise ModelError("at least two participants are required")
        rows = self._feature_engine.for_race(
            race_date=race_date,
            distance_meters=distance_meters,
            surface=surface,
            participants=participants,
            global_win_rate=self._global_win_rate,
        )
        participant_ids = tuple(participant.participant_id for participant in participants)
        frame = pd.DataFrame.from_records(
            [rows[participant_id] for participant_id in participant_ids],
            columns=LIGHTGBM_FEATURE_COLUMNS,
        )
        for column in CATEGORICAL_FEATURE_COLUMNS:
            frame[column] = frame[column].astype("category")
        try:
            predicted = np.asarray(self._estimator.predict_proba(frame), dtype=np.float64)
        except Exception as error:
            raise RealModelArtifactError("real model inference is incompatible") from error
        if predicted.shape != (len(participants), 2):
            raise RealModelArtifactError("real model returned an invalid probability shape")
        strengths = predicted[:, 1]
        if not np.isfinite(strengths).all() or np.any(strengths <= 0):
            raise RealModelArtifactError("real model returned invalid winner strengths")
        try:
            normalized = normalize_race_scores(participant_ids, strengths)
        except ValueError as error:
            raise RealModelArtifactError(str(error)) from error
        places = plackett_luce_place_probabilities(
            normalized, min(self._place_positions, len(participants))
        )
        fair_odds = {
            participant_id: 1.0 / probability for participant_id, probability in normalized.items()
        }
        return RealRacePrediction(
            win_probabilities=normalized,
            place_probabilities=places,
            fair_odds=fair_odds,
            metadata=self.metadata,
            distance_meters=distance_meters,
            surface=surface,
        )


class EnsembleRaceModel(RealLightGBMRaceModel):
    """Hash-pinned ensemble using the same feature and probability interface."""

    def __init__(
        self,
        *,
        estimator: EnsembleEstimator,
        feature_engine: HistoricalLightGBMFeatureEngine,
        artifact_sha256: str,
        place_positions: int,
        training_rows: int,
        training_start: date,
        training_end: date,
    ) -> None:
        super().__init__(
            estimator=estimator,
            feature_engine=feature_engine,
            global_win_rate=None,
            artifact_sha256=artifact_sha256,
            place_positions=place_positions,
        )
        self._ensemble_metadata = RealModelMetadata(
            "ensemble_v1",
            training_rows,
            training_start,
            training_end,
            artifact_sha256,
        )

    @property
    def metadata(self) -> RealModelMetadata:
        return self._ensemble_metadata

    def predict_race(
        self,
        *,
        race_date: date,
        distance_meters: int,
        surface: str,
        participants: tuple[RealRaceParticipant, ...],
    ) -> RealRacePrediction:
        if race_date <= self.metadata.training_end:
            raise ModelError("the prediction date must follow the model's training period")
        return super().predict_race(
            race_date=race_date,
            distance_meters=distance_meters,
            surface=surface,
            participants=participants,
        )

    @classmethod
    def load(
        cls, *, model_path: Path, dataset_path: Path, expected_sha256: str, place_positions: int = 3
    ) -> EnsembleRaceModel:
        if not model_path.is_file() or not dataset_path.is_file():
            raise RealModelArtifactError("ensemble artifact or historical dataset not found")
        if place_positions <= 0:
            raise RealModelArtifactError("place_positions must be positive")
        try:
            payload = model_path.read_bytes()
            digest = sha256(payload).hexdigest()
            if not compare_digest(digest, expected_sha256.casefold()):
                raise RealModelArtifactError("ensemble artifact SHA-256 mismatch")
            loaded: Any = pickle.loads(payload)
            if not isinstance(loaded, Mapping) or loaded.get("contract") != "ensemble-v1":
                raise RealModelArtifactError("unsupported ensemble artifact contract")
            if loaded["dataset_sha256"] != sha256(dataset_path.read_bytes()).hexdigest():
                raise RealModelArtifactError("historical dataset SHA-256 mismatch")
            if tuple(loaded["feature_columns"]) != LIGHTGBM_FEATURE_COLUMNS:
                raise RealModelArtifactError("ensemble feature column contract is incompatible")
            versions = {name: version(name) for name in ("lightgbm", "xgboost", "scikit-learn")}
            if loaded["versions"] != versions:
                raise RealModelArtifactError("incompatible ensemble library versions")
            models, weights, levels = loaded["models"], loaded["weights"], loaded["levels"]
            if models.keys() != MODEL_WEIGHTS.keys() or weights != MODEL_WEIGHTS:
                raise RealModelArtifactError("ensemble models or weights are incompatible")
            if levels.keys() != set(CATEGORICAL_FEATURE_COLUMNS):
                raise RealModelArtifactError("ensemble category encoding is incompatible")
            if any(
                not callable(getattr(model, "predict_proba", None))
                or getattr(model, "n_features_in_", None) != len(LIGHTGBM_FEATURE_COLUMNS)
                or list(model.classes_) != [0, 1]
                for model in models.values()
            ):
                raise RealModelArtifactError("ensemble estimator contract is incompatible")
            return cls(
                estimator=EnsembleEstimator(models, weights, levels),
                feature_engine=HistoricalLightGBMFeatureEngine(dataset_path),
                artifact_sha256=digest,
                place_positions=place_positions,
                training_rows=int(loaded["train_rows"]),
                training_start=date.fromisoformat(loaded["training_start"]),
                training_end=date.fromisoformat(loaded["training_end"]),
            )
        except RealModelArtifactError:
            raise
        except Exception as error:
            raise RealModelArtifactError("ensemble artifact could not be loaded") from error


def encode_feature_vector(features: FeatureVector) -> NDArray[np.float64]:
    """Encode the public FeatureVector in one stable numerical column order."""

    values = [
        features["starts_total"],
        features["wins_total"],
        features["win_rate"],
        features["podium_rate"],
        365.0 if features["days_since_last_race"] is None else features["days_since_last_race"],
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

    def generate(self, *, race_count: int = 500, field_size: int = 7) -> SyntheticTrainingSet:
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
            "days_since_last_race": (None if rng.random() < 0.05 else int(rng.integers(5, 366))),
            "distance_starts": distance_starts,
            "distance_wins": distance_wins,
            "distance_win_rate": distance_wins / distance_starts if distance_starts else 0.0,
            "distance_podium_rate": (
                distance_podiums / distance_starts if distance_starts else 0.0
            ),
            "distance_average_position": (float(rng.uniform(1, 7)) if distance_starts else 0.0),
            "surface_starts": surface_starts,
            "surface_wins": surface_wins,
            "surface_win_rate": surface_wins / surface_starts if surface_starts else 0.0,
            "surface_podium_rate": (surface_podiums / surface_starts if surface_starts else 0.0),
            "surface_average_position": (float(rng.uniform(1, 7)) if surface_starts else 0.0),
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

    def fit_synthetic(self, *, race_count: int = 500, field_size: int = 7) -> BaselineRaceModel:
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

    def predict_race(self, participants: Mapping[str, FeatureVector]) -> RacePrediction:
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
