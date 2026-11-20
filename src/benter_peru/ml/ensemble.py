"""Shared encoding and probability combination for training and serving."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from numpy.typing import NDArray

from benter_peru.ml.real_features import CATEGORICAL_FEATURE_COLUMNS, LIGHTGBM_FEATURE_COLUMNS

MODEL_WEIGHTS: Mapping[str, float] = {"lightgbm": 0.4, "xgboost": 0.4, "random_forest": 0.2}


class Classifier(Protocol):
    def predict_proba(self, values: pd.DataFrame) -> object: ...


def category_levels(frame: pd.DataFrame) -> dict[str, tuple[str, ...]]:
    return {
        column: tuple(sorted(frame[column].astype(str).unique()))
        for column in CATEGORICAL_FEATURE_COLUMNS
    }


def encode(frame: pd.DataFrame, levels: Mapping[str, Sequence[str]]) -> pd.DataFrame:
    result = frame[list(LIGHTGBM_FEATURE_COLUMNS)].copy()
    for column in CATEGORICAL_FEATURE_COLUMNS:
        categories = pd.Index(levels[column])
        codes = categories.get_indexer(result[column])
        result[column] = pd.Categorical.from_codes(codes, categories=categories).codes
    return result


def blend_winner_scores(
    scores: Mapping[str, NDArray[np.float64]], weights: Mapping[str, float]
) -> NDArray[np.float64]:
    if scores.keys() != MODEL_WEIGHTS.keys() or dict(weights) != MODEL_WEIGHTS:
        raise ValueError("ensemble models or weights do not match the fixed contract")
    arrays = [np.asarray(scores[name], dtype=np.float64) for name in MODEL_WEIGHTS]
    if any(
        a.ndim != 1
        or a.shape != arrays[0].shape
        or not np.isfinite(a).all()
        or np.any((a < 0) | (a > 1))
        for a in arrays
    ):
        raise ValueError("invalid ensemble winner probabilities")
    return np.average(np.stack(arrays), axis=0, weights=list(MODEL_WEIGHTS.values()))


def normalize_race_scores(ids: Sequence[str], scores: NDArray[np.float64]) -> dict[str, float]:
    if not ids or len(ids) != len(scores) or len(set(ids)) != len(ids):
        raise ValueError("invalid participant IDs for race normalization")
    if not np.isfinite(scores).all() or np.any(scores <= 0):
        raise ValueError("race scores must be finite and positive")
    total = float(scores.sum())
    normalized = {
        name: float(value / total) for name, value in zip(ids[:-1], scores[:-1], strict=True)
    }
    normalized[ids[-1]] = 1.0 - sum(normalized.values())
    if normalized[ids[-1]] <= 0:
        raise ValueError("race normalization produced invalid probabilities")
    return normalized


def winner_scores(model: Classifier, frame: pd.DataFrame) -> NDArray[np.float64]:
    predicted = np.asarray(model.predict_proba(frame), dtype=np.float64)
    if predicted.shape != (len(frame), 2):
        raise ValueError("ensemble estimator returned an invalid probability shape")
    return predicted[:, 1]


@dataclass(frozen=True, slots=True)
class EnsembleEstimator:
    models: Mapping[str, Classifier]
    weights: Mapping[str, float]
    levels: Mapping[str, Sequence[str]]

    @property
    def n_features_in_(self) -> int:
        return len(LIGHTGBM_FEATURE_COLUMNS)

    def predict_proba(self, frame: pd.DataFrame) -> NDArray[np.float64]:
        values = encode(frame, self.levels)
        scores = blend_winner_scores(
            {name: winner_scores(model, values) for name, model in self.models.items()},
            self.weights,
        )
        return np.column_stack((1.0 - scores, scores))
