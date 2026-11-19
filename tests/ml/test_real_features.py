"""Leakage-safe historical LightGBM feature tests."""

from datetime import date
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

from benter_peru.ml.real_features import (
    LIGHTGBM_FEATURE_COLUMNS,
    HistoricalFeatureError,
    HistoricalLightGBMFeatureEngine,
    RealRaceParticipant,
)


def _write_history(path: Path) -> None:
    pd.DataFrame.from_records(
        [
            {
                "Fecha": "2026-01-01",
                "Posicion": "1",
                "Caballo": "HORSE A",
                "Jinete": "JOCKEY A",
                "Preparador": "TRAINER A",
                "Stud": "STUD A",
                "Edad": 2,
            },
            {
                "Fecha": "2026-02-01",
                "Posicion": "2",
                "Caballo": "HORSE A",
                "Jinete": "JOCKEY A",
                "Preparador": "TRAINER A",
                "Stud": "STUD A",
                "Edad": 3,
            },
            {
                "Fecha": "2026-03-01",
                "Posicion": "1",
                "Caballo": "HORSE B",
                "Jinete": "JOCKEY B",
                "Preparador": "TRAINER B",
                "Stud": "STUD B",
                "Edad": 4,
            },
            {
                "Fecha": "2026-11-22",
                "Posicion": "1",
                "Caballo": "HORSE A",
                "Jinete": "JOCKEY A",
                "Preparador": "TRAINER A",
                "Stud": "STUD A",
                "Edad": 9,
            },
        ]
    ).to_csv(path, index=False)


def _participants() -> tuple[RealRaceParticipant, ...]:
    return (
        RealRaceParticipant(
            participant_id="horse-a",
            horse_name="HORSE A",
            jockey_name="JOCKEY A",
            trainer_name="TRAINER A",
            stud_name="STUD A",
            weight=56.0,
            mandil=1,
        ),
        RealRaceParticipant(
            participant_id="horse-b",
            horse_name="HORSE B",
            jockey_name="JOCKEY B",
            trainer_name="TRAINER B",
            stud_name="STUD B",
            weight=54.0,
            mandil=2,
        ),
    )


def test_feature_engine_emits_exact_training_columns_and_smoothed_values(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "history.csv"
    _write_history(dataset)
    engine = HistoricalLightGBMFeatureEngine(dataset)

    rows = engine.for_race(
        race_date=date(2026, 11, 22),
        distance_meters=1000,
        surface="arena",
        participants=_participants(),
        global_win_rate=0.2,
    )

    horse_a = rows["horse-a"]
    assert tuple(horse_a) == LIGHTGBM_FEATURE_COLUMNS
    assert horse_a["Jinete_Carreras_Prev"] == 2.0
    assert horse_a["Jinete_WinRate_Smoothed"] == pytest.approx(2 / 7)
    assert horse_a["Caballo_Carreras_Prev"] == 2.0
    assert horse_a["Caballo_WinRate_Smoothed"] == pytest.approx(0.35)
    assert horse_a["Caballo_Puesto_Prom_Hist"] == 1.5
    assert horse_a["Duo_WinRate_Smoothed"] == pytest.approx(0.35)
    assert horse_a["Edad_Num"] == 3.0
    assert horse_a["Distancia_Num"] == 1000.0
    assert horse_a["Competidores_Carrera"] == 2.0
    assert horse_a["Prob_Base_Lote"] == 0.5


def test_feature_engine_uses_selected_race_distance_for_any_race(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "history.csv"
    _write_history(dataset)
    engine = HistoricalLightGBMFeatureEngine(dataset)

    sprint = engine.for_race(
        race_date=date(2026, 11, 22),
        distance_meters=1000,
        surface="arena",
        participants=_participants(),
        global_win_rate=0.2,
    )
    derby = engine.for_race(
        race_date=date(2026, 11, 22),
        distance_meters=2400,
        surface="arena",
        participants=_participants(),
        global_win_rate=0.2,
    )

    assert {row["Distancia_Num"] for row in sprint.values()} == {1000.0}
    assert {row["Distancia_Num"] for row in derby.values()} == {2400.0}


def test_feature_engine_rejects_horse_without_prior_age(tmp_path: Path) -> None:
    dataset = tmp_path / "history.csv"
    _write_history(dataset)
    unknown = RealRaceParticipant(
        participant_id="unknown",
        horse_name="UNKNOWN",
        jockey_name="JOCKEY A",
        trainer_name="TRAINER A",
        stud_name="STUD A",
        weight=55.0,
        mandil=9,
    )

    with pytest.raises(HistoricalFeatureError, match=r"UNKNOWN.*prior history"):
        HistoricalLightGBMFeatureEngine(dataset).for_race(
            race_date=date(2026, 11, 22),
            distance_meters=1200,
            surface="arena",
            participants=(unknown,),
            global_win_rate=0.2,
        )


def test_feature_engine_rejects_ambiguous_normalized_horse(tmp_path: Path) -> None:
    dataset = tmp_path / "history.csv"
    pd.DataFrame.from_records(
        [
            {
                "Fecha": "2026-01-01",
                "Posicion": "1",
                "Caballo": "Mr. Peggy",
                "Jinete": "J",
                "Preparador": "P",
                "Stud": "S",
                "Edad": 3,
            },
            {
                "Fecha": "2026-02-01",
                "Posicion": "2",
                "Caballo": "MR PEGGY",
                "Jinete": "J",
                "Preparador": "P",
                "Stud": "S",
                "Edad": 3,
            },
        ]
    ).to_csv(dataset, index=False)
    participant = RealRaceParticipant(
        participant_id="peggy",
        horse_name="Mr Peggy",
        jockey_name="J",
        trainer_name="P",
        stud_name="S",
        weight=56.0,
        mandil=4,
    )

    with pytest.raises(HistoricalFeatureError, match="ambiguous horse identity"):
        HistoricalLightGBMFeatureEngine(dataset).for_race(
            race_date=date(2026, 11, 22),
            distance_meters=2400,
            surface="arena",
            participants=(participant,),
            global_win_rate=0.2,
        )
