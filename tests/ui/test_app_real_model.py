"""Dashboard real-artifact startup boundary tests."""

from pathlib import Path

import pytest

from benter_peru.ml.artifacts import RealModelArtifactConfig
from benter_peru.ml.models import RealModelArtifactError
from benter_peru.ui.app import ARTIFACT_ERROR_MESSAGE, _load_prediction_service


def test_dashboard_service_loader_fails_closed_with_friendly_contract(
    tmp_path: Path,
) -> None:
    config = RealModelArtifactConfig(
        model_path=tmp_path / "missing.pkl",
        dataset_path=tmp_path / "missing.csv",
    )

    with pytest.raises(RealModelArtifactError):
        _load_prediction_service(config)
    assert ARTIFACT_ERROR_MESSAGE == (
        "Error: Artefactos del modelo no encontrados o corruptos. "
        "Por favor, ejecute el pipeline de entrenamiento."
    )
