"""Real-model operational entry point tests."""

from pathlib import Path

from benter_peru.ml.entrenar_modelo import build_parser as build_training_parser
from benter_peru.ml.predecir_derby import build_parser as build_prediction_parser


def test_training_cli_requires_explicit_artifact_paths() -> None:
    arguments = build_training_parser().parse_args(
        ["--dataset", "history.csv", "--output", "model.pkl"]
    )

    assert arguments.dataset == Path("history.csv")
    assert arguments.output == Path("model.pkl")


def test_prediction_cli_selects_any_registered_race() -> None:
    arguments = build_prediction_parser().parse_args(
        [
            "--database",
            "benter.sqlite3",
            "--meeting",
            "202647",
            "--race",
            "1",
        ]
    )

    assert arguments.database == Path("benter.sqlite3")
    assert arguments.meeting == "202647"
    assert arguments.race == 1
