"""Local real-model artifact configuration tests."""

from pathlib import Path

from benter_peru.ml.artifacts import RealModelArtifactConfig


def test_artifact_config_uses_pinned_local_defaults() -> None:
    config = RealModelArtifactConfig.from_env({})

    assert config.model_path == Path("var/ml/real-model/modelo_hipico_v1.pkl")
    assert config.dataset_path == Path(
        "var/ml/real-model/dataset_oficial_resultados.csv"
    )
    assert config.expected_sha256 == (
        "18c751b283a5af4461e5f9c16604e135bf56b00d0241f3f6c6c14e7d4537852f"
    )


def test_artifact_config_allows_paths_but_not_digest_from_environment() -> None:
    config = RealModelArtifactConfig.from_env(
        {
            "BENTER_REAL_MODEL_PATH": "D:/models/model.pkl",
            "BENTER_REAL_DATASET_PATH": "D:/data/history.csv",
            "BENTER_REAL_MODEL_SHA256": "0" * 64,
        }
    )

    assert config.model_path == Path("D:/models/model.pkl")
    assert config.dataset_path == Path("D:/data/history.csv")
    assert config.expected_sha256.startswith("18c751b2")
