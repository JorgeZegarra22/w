"""Hash-pinned historical LightGBM model tests."""

import pickle
from datetime import date
from hashlib import sha256
from pathlib import Path

import lightgbm as lgb  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
import pytest

from benter_peru.ml.models import RealLightGBMRaceModel, RealModelArtifactError
from benter_peru.ml.real_features import (
    CATEGORICAL_FEATURE_COLUMNS,
    LIGHTGBM_FEATURE_COLUMNS,
    RealRaceParticipant,
)


def _dataset(path: Path) -> None:
    pd.DataFrame.from_records(
        [
            {
                "Fecha": "2026-01-01",
                "Posicion": "1",
                "Caballo": "ALPHA",
                "Jinete": "J A",
                "Preparador": "P A",
                "Stud": "S A",
                "Edad": 3,
            },
            {
                "Fecha": "2026-02-01",
                "Posicion": "2",
                "Caballo": "ALPHA",
                "Jinete": "J A",
                "Preparador": "P A",
                "Stud": "S A",
                "Edad": 3,
            },
            {
                "Fecha": "2026-01-01",
                "Posicion": "2",
                "Caballo": "BETA",
                "Jinete": "J B",
                "Preparador": "P B",
                "Stud": "S B",
                "Edad": 4,
            },
            {
                "Fecha": "2026-02-01",
                "Posicion": "1",
                "Caballo": "BETA",
                "Jinete": "J B",
                "Preparador": "P B",
                "Stud": "S B",
                "Edad": 4,
            },
        ]
    ).to_csv(path, index=False)


def _training_frame() -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for index in range(8):
        rows.append(
            {
                "Jinete_WinRate_Smoothed": 0.1 + index * 0.05,
                "Jinete_Carreras_Prev": float(index + 1),
                "Preparador_WinRate_Smoothed": 0.2,
                "Preparador_Carreras_Prev": 5.0,
                "Caballo_WinRate_Smoothed": 0.15 + index * 0.03,
                "Caballo_Carreras_Prev": 3.0,
                "Caballo_Puesto_Prom_Hist": 4.0 - index * 0.2,
                "Stud_WinRate_Smoothed": 0.2,
                "Duo_WinRate_Smoothed": 0.2,
                "Peso_Num": 54.0 + index % 3,
                "Distancia_Num": 1000.0 + (index % 2) * 400,
                "Edad_Num": 3.0 + index % 2,
                "Mandil_Num": float(index + 1),
                "Competidores_Carrera": 4.0,
                "Prob_Base_Lote": 0.25,
                "Jinete_Limpio": "J A" if index % 2 == 0 else "J B",
                "Prep_Limpio": "P A" if index % 2 == 0 else "P B",
                "Stud_Limpio": "S A" if index % 2 == 0 else "S B",
            }
        )
    frame = pd.DataFrame.from_records(rows, columns=LIGHTGBM_FEATURE_COLUMNS)
    for column in CATEGORICAL_FEATURE_COLUMNS:
        frame[column] = frame[column].astype("category")
    return frame


def _artifact(
    path: Path, *, feature_columns: tuple[str, ...] = LIGHTGBM_FEATURE_COLUMNS
) -> str:
    frame = _training_frame()
    model = lgb.LGBMClassifier(
        n_estimators=5,
        min_child_samples=1,
        num_leaves=4,
        random_state=7,
        verbose=-1,
    )
    model.fit(frame, [0, 1, 0, 1, 0, 1, 0, 1])
    with path.open("wb") as stream:
        pickle.dump(
            {
                "model": model,
                "feature_cols": list(feature_columns),
                "categorical_cols": list(CATEGORICAL_FEATURE_COLUMNS),
                "global_win_rate": 0.25,
            },
            stream,
        )
    return sha256(path.read_bytes()).hexdigest()


def _participants() -> tuple[RealRaceParticipant, ...]:
    return (
        RealRaceParticipant("alpha", "ALPHA", "J A", "P A", "S A", 56.0, 1),
        RealRaceParticipant("beta", "BETA", "J B", "P B", "S B", 54.0, 2),
    )


def test_real_model_fails_closed_for_missing_artifacts(tmp_path: Path) -> None:
    dataset = tmp_path / "history.csv"
    _dataset(dataset)

    with pytest.raises(RealModelArtifactError, match="model artifact not found"):
        RealLightGBMRaceModel.load(
            model_path=tmp_path / "missing.pkl",
            dataset_path=dataset,
            expected_sha256="0" * 64,
        )
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"not loaded")
    with pytest.raises(RealModelArtifactError, match="historical dataset not found"):
        RealLightGBMRaceModel.load(
            model_path=model_path,
            dataset_path=tmp_path / "missing.csv",
            expected_sha256=sha256(b"not loaded").hexdigest(),
        )


def test_real_model_rejects_wrong_hash_before_deserialization(tmp_path: Path) -> None:
    dataset = tmp_path / "history.csv"
    _dataset(dataset)
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"not a pickle")

    with pytest.raises(RealModelArtifactError, match="SHA-256 mismatch"):
        RealLightGBMRaceModel.load(
            model_path=model_path,
            dataset_path=dataset,
            expected_sha256="0" * 64,
        )


def test_real_model_rejects_incompatible_feature_order(tmp_path: Path) -> None:
    dataset = tmp_path / "history.csv"
    _dataset(dataset)
    model_path = tmp_path / "model.pkl"
    digest = _artifact(model_path, feature_columns=tuple(reversed(LIGHTGBM_FEATURE_COLUMNS)))

    with pytest.raises(RealModelArtifactError, match="feature column contract"):
        RealLightGBMRaceModel.load(
            model_path=model_path,
            dataset_path=dataset,
            expected_sha256=digest,
        )


def test_real_model_predicts_selected_race_and_exact_fair_odds(tmp_path: Path) -> None:
    dataset = tmp_path / "history.csv"
    _dataset(dataset)
    model_path = tmp_path / "model.pkl"
    digest = _artifact(model_path)
    model = RealLightGBMRaceModel.load(
        model_path=model_path,
        dataset_path=dataset,
        expected_sha256=digest,
        place_positions=2,
    )

    prediction = model.predict_race(
        race_date=date(2026, 11, 22),
        distance_meters=1000,
        surface="arena",
        participants=_participants(),
    )

    assert sum(prediction.win_probabilities.values()) == 1.0
    assert sum(prediction.place_probabilities.values()) == pytest.approx(2.0)
    assert all(value > 0 for value in prediction.win_probabilities.values())
    for participant_id, probability in prediction.win_probabilities.items():
        assert prediction.fair_odds[participant_id] == pytest.approx(1 / probability)
    assert prediction.metadata.model_type == "historical_lightgbm_v1"
    assert prediction.metadata.training_rows == 4
    assert prediction.distance_meters == 1000
    assert prediction.surface == "arena"
