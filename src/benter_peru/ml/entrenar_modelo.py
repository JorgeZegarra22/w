"""Command-line training entry point for a versioned LightGBM artifact."""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import lightgbm as lgb
import pandas as pd  # type: ignore[import-untyped]

from benter_peru.ml.real_features import (
    CATEGORICAL_FEATURE_COLUMNS,
    LIGHTGBM_FEATURE_COLUMNS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m benter_peru.ml.entrenar_modelo")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _shifted_statistics(
    frame: pd.DataFrame,
    *,
    identity: str,
    global_rate: float,
    prior_weight: float,
) -> tuple[pd.Series, pd.Series]:
    grouped = frame.groupby(identity, sort=False)["Target_Ganador"]
    wins = grouped.transform(lambda values: values.shift(1).expanding().sum()).fillna(0)
    starts = grouped.transform(lambda values: values.shift(1).expanding().count()).fillna(0)
    return (wins + prior_weight * global_rate) / (starts + prior_weight), starts


def prepare_training_frame(dataset_path: Path) -> pd.DataFrame:
    """Rebuild the artifact's leakage-safe training frame in chronological order."""
    frame = pd.read_csv(dataset_path)
    frame["Fecha_Dt"] = pd.to_datetime(frame["Fecha"], errors="raise")
    frame["Carrera_Num"] = pd.to_numeric(frame["Carrera"], errors="coerce").fillna(1)
    frame["Mandil_Num"] = pd.to_numeric(
        frame["Numero_Mandil"], errors="coerce"
    ).fillna(99)
    frame = frame.sort_values(["Fecha_Dt", "Carrera_Num", "Mandil_Num"]).reset_index(
        drop=True
    )
    frame["Target_Ganador"] = (
        frame["Posicion"].astype(str).str.strip() == "1"
    ).astype(int)
    global_rate = float(frame["Target_Ganador"].mean())
    for source, target in (
        ("Jinete", "Jinete_Limpio"),
        ("Preparador", "Prep_Limpio"),
        ("Caballo", "Caballo_Limpio"),
        ("Stud", "Stud_Limpio"),
    ):
        frame[target] = frame[source].fillna("DESCONOCIDO").astype(str).str.strip()

    frame["Jinete_WinRate_Smoothed"], frame["Jinete_Carreras_Prev"] = (
        _shifted_statistics(
            frame,
            identity="Jinete_Limpio",
            global_rate=global_rate,
            prior_weight=5.0,
        )
    )
    frame["Preparador_WinRate_Smoothed"], frame["Preparador_Carreras_Prev"] = (
        _shifted_statistics(
            frame,
            identity="Prep_Limpio",
            global_rate=global_rate,
            prior_weight=5.0,
        )
    )
    frame["Caballo_WinRate_Smoothed"], frame["Caballo_Carreras_Prev"] = (
        _shifted_statistics(
            frame,
            identity="Caballo_Limpio",
            global_rate=global_rate,
            prior_weight=2.0,
        )
    )
    frame["Stud_WinRate_Smoothed"], _ = _shifted_statistics(
        frame,
        identity="Stud_Limpio",
        global_rate=global_rate,
        prior_weight=5.0,
    )
    frame["Duo_JP"] = frame["Jinete_Limpio"] + " & " + frame["Prep_Limpio"]
    frame["Duo_WinRate_Smoothed"], _ = _shifted_statistics(
        frame,
        identity="Duo_JP",
        global_rate=global_rate,
        prior_weight=2.0,
    )
    positions = pd.to_numeric(frame["Posicion"], errors="coerce").fillna(8.0)
    frame["Caballo_Puesto_Prom_Hist"] = positions.groupby(
        frame["Caballo_Limpio"], sort=False
    ).transform(lambda values: values.shift(1).expanding().mean()).fillna(5.0)
    frame["Peso_Num"] = pd.to_numeric(
        frame["Peso"].astype(str).str.extract(r"(\d+(?:\.\d+)?)")[0],
        errors="coerce",
    ).fillna(55.0)
    frame["Distancia_Num"] = pd.to_numeric(
        frame["Distancia"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
    ).fillna(1000.0)
    frame["Edad_Num"] = pd.to_numeric(frame["Edad"], errors="coerce").fillna(4.0)
    race_keys = ["Fecha", "Carrera_Num"]
    frame["Competidores_Carrera"] = frame.groupby(race_keys)["Caballo"].transform(
        "count"
    )
    frame["Prob_Base_Lote"] = 1.0 / frame["Competidores_Carrera"].clip(lower=2)
    for column in CATEGORICAL_FEATURE_COLUMNS:
        frame[column] = frame[column].astype("category")
    return frame


def train_model(dataset_path: Path, output_path: Path) -> None:
    """Train and serialize the exact artifact contract consumed by inference."""
    frame = prepare_training_frame(dataset_path)
    dates = sorted(frame["Fecha_Dt"].unique())
    cutoff = dates[int(len(dates) * 0.8)]
    train = frame[frame["Fecha_Dt"] < cutoff]
    validation = frame[frame["Fecha_Dt"] >= cutoff]
    model = lgb.LGBMClassifier(
        objective="binary",
        learning_rate=0.03,
        n_estimators=500,
        num_leaves=31,
        max_depth=6,
        min_child_samples=25,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=-1,
    )
    model.fit(
        train[list(LIGHTGBM_FEATURE_COLUMNS)],
        train["Target_Ganador"],
        eval_set=[
            (
                validation[list(LIGHTGBM_FEATURE_COLUMNS)],
                validation["Target_Ganador"],
            )
        ],
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    artifact = {
        "model": model,
        "feature_cols": list(LIGHTGBM_FEATURE_COLUMNS),
        "categorical_cols": list(CATEGORICAL_FEATURE_COLUMNS),
        "global_win_rate": float(frame["Target_Ganador"].mean()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as stream:
        pickle.dump(artifact, stream)


def main() -> None:
    arguments = build_parser().parse_args()
    train_model(arguments.dataset, arguments.output)


if __name__ == "__main__":
    main()
