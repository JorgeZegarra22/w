"""Dashboard real-artifact startup boundary tests."""

from pathlib import Path

import pytest

from benter_peru.ml.artifacts import EnsembleArtifactConfig
from benter_peru.ml.models import RealModelArtifactError
from benter_peru.ui.app import ARTIFACT_ERROR_MESSAGE, _load_prediction_service
from benter_peru.ui.paths import project_path


def test_dashboard_paths_use_checkout_root_from_outside_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    assert project_path("var/benter.sqlite3") == root / "var/benter.sqlite3"
    assert project_path("estilos_domingo_2026.csv") == root / "estilos_domingo_2026.csv"
    assert project_path(tmp_path / "custom.sqlite3") == tmp_path / "custom.sqlite3"


def test_dashboard_service_loader_fails_closed_with_friendly_contract(
    tmp_path: Path,
) -> None:
    config = EnsembleArtifactConfig(
        model_path=tmp_path / "missing.pkl",
        dataset_path=tmp_path / "missing.csv",
    )

    with pytest.raises(RealModelArtifactError):
        _load_prediction_service(config)
    assert ARTIFACT_ERROR_MESSAGE == (
        "Error: Artefactos del modelo no encontrados o corruptos. "
        "Por favor, ejecute el pipeline de entrenamiento."
    )
