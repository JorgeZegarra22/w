"""Synthetic logistic baseline and race-level prediction tests."""

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from benter_peru.ml.features import FeatureVector
from benter_peru.ml.models import (
    BaselineRaceModel,
    ModelNotFittedError,
    SyntheticRaceGenerator,
    encode_feature_vector,
)


def _features(**overrides: int | float | None) -> FeatureVector:
    values: FeatureVector = {
        "starts_total": 5,
        "wins_total": 2,
        "win_rate": 0.4,
        "podium_rate": 0.6,
        "days_since_last_race": 28,
        "distance_starts": 3,
        "distance_wins": 1,
        "distance_win_rate": 0.333333,
        "distance_podium_rate": 0.666667,
        "distance_average_position": 2.666667,
        "surface_starts": 5,
        "surface_wins": 2,
        "surface_win_rate": 0.4,
        "surface_podium_rate": 0.6,
        "surface_average_position": 2.8,
    }
    values.update(overrides)  # type: ignore[typeddict-item]
    return values


def test_feature_encoder_has_stable_order_and_imputes_missing_recency() -> None:
    encoded = encode_feature_vector(_features(days_since_last_race=None))

    assert encoded.shape == (15,)
    assert encoded.tolist() == [
        5.0,
        2.0,
        0.4,
        0.6,
        365.0,
        3.0,
        1.0,
        0.333333,
        0.666667,
        2.666667,
        5.0,
        2.0,
        0.4,
        0.6,
        2.8,
    ]


def test_synthetic_generator_is_reproducible_and_has_one_winner_per_race() -> None:
    first = SyntheticRaceGenerator(random_state=20261118).generate()
    second = SyntheticRaceGenerator(random_state=20261118).generate()

    assert first.features.shape == (3500, 15)
    assert first.labels.shape == (3500,)
    assert first.groups.shape == (3500,)
    assert np.array_equal(first.features, second.features)
    assert np.array_equal(first.labels, second.labels)
    assert np.array_equal(first.groups, second.groups)
    assert all(first.labels[first.groups == group].sum() == 1 for group in range(500))


def test_prediction_requires_fitted_model() -> None:
    with pytest.raises(ModelNotFittedError):
        BaselineRaceModel().predict_race({"a": _features(), "b": _features()})


def test_model_pipeline_predicts_exact_race_and_top_three_distributions() -> None:
    model = BaselineRaceModel(place_positions=3).fit_synthetic()
    participants = {
        f"horse-{index}": _features(
            win_rate=0.1 * index,
            podium_rate=min(1.0, 0.2 * index),
            days_since_last_race=10 * index,
        )
        for index in range(1, 8)
    }

    prediction = model.predict_race(participants)

    assert isinstance(model.pipeline.named_steps["scaler"], StandardScaler)
    assert isinstance(model.pipeline.named_steps["logistic"], LogisticRegression)
    assert all(value > 0 for value in prediction.win_probabilities.values())
    assert sum(prediction.win_probabilities.values()) == 1.0
    assert sum(prediction.place_probabilities.values()) == pytest.approx(3.0, abs=1e-12)
    assert all(0 <= value <= 1 for value in prediction.place_probabilities.values())
    assert prediction.metadata.model_type == "synthetic_softmax_baseline"
    assert prediction.metadata.production_ready is False
    assert prediction.metadata.calibrated is False
    assert prediction.metadata.race_count == 500
    assert prediction.metadata.field_size == 7


def test_model_is_reproducible_and_permutation_invariant() -> None:
    participants = {
        "a": _features(win_rate=0.2, podium_rate=0.4),
        "b": _features(win_rate=0.5, podium_rate=0.8),
        "c": _features(win_rate=0.1, podium_rate=0.3),
    }
    first_model = BaselineRaceModel(place_positions=2, random_state=9).fit_synthetic(
        race_count=50, field_size=4
    )
    second_model = BaselineRaceModel(place_positions=2, random_state=9).fit_synthetic(
        race_count=50, field_size=4
    )

    first = first_model.predict_race(participants)
    repeated = second_model.predict_race(participants)
    reversed_prediction = first_model.predict_race(dict(reversed(tuple(participants.items()))))

    assert first.win_probabilities == repeated.win_probabilities
    for participant_id in participants:
        assert first.win_probabilities[participant_id] == pytest.approx(
            reversed_prediction.win_probabilities[participant_id], abs=1e-15
        )
        assert first.place_probabilities[participant_id] == pytest.approx(
            reversed_prediction.place_probabilities[participant_id], abs=1e-15
        )
