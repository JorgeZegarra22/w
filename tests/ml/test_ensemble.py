from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import pytest

from benter_peru.ml.clean_training import clean_features, temporal_split
from benter_peru.ml.ensemble import (
    MODEL_WEIGHTS,
    EnsembleEstimator,
    blend_winner_scores,
    normalize_race_scores,
)
from benter_peru.ml.models import EnsembleRaceModel, ModelError, RealModelArtifactError
from benter_peru.ml.real_features import (
    CATEGORICAL_FEATURE_COLUMNS,
    HistoricalLightGBMFeatureEngine,
    RealRaceParticipant,
)


def test_features_only_see_previous_dates() -> None:
    raw = pd.DataFrame(
        {
            "Fecha": ["2026-05-14", "2026-05-15", "2026-05-15", "2026-05-16"],
            "Carrera": [1, 1, 2, 1],
            "Numero_Mandil": [1, 1, 1, 1],
            "Caballo": ["A"] * 4,
            "Jinete": ["J"] * 4,
            "Preparador": ["P"] * 4,
            "Stud": ["S"] * 4,
            "Posicion": [1, 2, 1, 9],
            "Edad": [3, 4, 4, 5],
            "Peso": [55] * 4,
            "Distancia": [1000] * 4,
        }
    )
    frame = clean_features(raw)
    assert frame["Jinete_Carreras_Prev"].tolist() == [0, 1, 1, 3]
    assert frame["Caballo_Puesto_Prom_Hist"].tolist() == [5, 1, 1, 4 / 3]
    assert frame["Edad_Num"].tolist() == [4, 3, 3, 4]
    assert frame["Jinete_WinRate_Smoothed"].tolist()[1:3] == [1, 1]
    changed = raw.copy()
    changed.loc[1:, "Posicion"] = 9
    assert (
        clean_features(changed)["Jinete_WinRate_Smoothed"].tolist()[:3]
        == (frame["Jinete_WinRate_Smoothed"].tolist()[:3])
    )
    train, validation, cutoff = temporal_split(frame)
    assert len(train) == 3 and len(validation) == 1
    assert str(cutoff.date()) == "2026-05-16"


def test_fixed_weight_ensemble_blends_before_race_normalization() -> None:
    scores = blend_winner_scores(
        {
            "lightgbm": np.array([0.4, 0.1, 0.2]),
            "xgboost": np.array([0.1, 0.4, 0.3]),
            "random_forest": np.array([0.5, 0.5, 0.0]),
        },
        MODEL_WEIGHTS,
    )
    assert scores.tolist() == pytest.approx([0.3, 0.3, 0.2])
    probabilities = normalize_race_scores(("a", "b", "c"), scores)
    assert list(probabilities.values()) == pytest.approx([0.375, 0.375, 0.25])
    assert sum(probabilities.values()) == 1.0


def test_predict_race_uses_weighted_scores_and_returns_exact_total(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    pd.DataFrame(
        [
            {
                "Fecha": "2026-01-01",
                "Posicion": 1,
                "Caballo": "A",
                "Jinete": "J",
                "Preparador": "P",
                "Stud": "S",
                "Edad": 3,
            }
        ]
    ).to_csv(path, index=False)

    class Fixed:
        def __init__(self, values: tuple[float, float]) -> None:
            self.values = np.array(values)

        def predict_proba(self, frame: pd.DataFrame) -> object:
            assert frame.shape == (2, 18)
            assert frame["Jinete_Limpio"].tolist() == [0, -1]
            return np.column_stack((1 - self.values, self.values))

    fitted = EnsembleEstimator(
        {
            "lightgbm": Fixed((0.4, 0.1)),
            "xgboost": Fixed((0.1, 0.4)),
            "random_forest": Fixed((0.5, 0.0)),
        },
        MODEL_WEIGHTS,
        dict(zip(CATEGORICAL_FEATURE_COLUMNS, (("J",), ("P",), ("S",)), strict=True)),
    )
    model = EnsembleRaceModel(
        estimator=fitted,
        feature_engine=HistoricalLightGBMFeatureEngine(path),
        artifact_sha256="a" * 64,
        place_positions=3,
        training_rows=1,
        training_start=date(2026, 1, 1),
        training_end=date(2026, 1, 1),
    )
    entries = (
        RealRaceParticipant("a", "A", "J", "P", "S", 55.0, 1),
        RealRaceParticipant("b", "B", "New", "P", "S", 54.0, 2),
    )
    result = model.predict_race(
        race_date=date(2026, 1, 2),
        distance_meters=1000,
        surface="arena",
        participants=entries,
    )
    assert result.win_probabilities == pytest.approx({"a": 0.6, "b": 0.4})
    assert sum(result.win_probabilities.values()) == 1.0
    with pytest.raises(ModelError, match="training period"):
        model.predict_race(
            race_date=date(2026, 1, 1),
            distance_meters=1000,
            surface="arena",
            participants=entries,
        )


def test_ensemble_checks_model_digest_before_loading(tmp_path: Path) -> None:
    artifact, dataset = tmp_path / "ensemble.pkl", tmp_path / "history.csv"
    artifact.write_bytes(b"not a pickle")
    dataset.touch()
    with pytest.raises(RealModelArtifactError, match="artifact SHA-256 mismatch"):
        EnsembleRaceModel.load(model_path=artifact, dataset_path=dataset, expected_sha256="a" * 64)
