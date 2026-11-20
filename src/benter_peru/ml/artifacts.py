"""Pinned local artifact configuration for the historical LightGBM model."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REAL_MODEL_V1_SHA256 = "18c751b283a5af4461e5f9c16604e135bf56b00d0241f3f6c6c14e7d4537852f"
DEFAULT_REAL_MODEL_PATH = Path("var/ml/real-model/modelo_hipico_v1.pkl")
DEFAULT_ENSEMBLE_MODEL_PATH = Path("var/ml/real-model/ensemble_model_v1.pkl")
ENSEMBLE_MODEL_V1_SHA256 = "55d84731e63522ca111ec3a1b64c3294a49105ba03aac4897e31a18c00cda2fd"
DEFAULT_REAL_DATASET_PATH = Path("var/ml/real-model/dataset_oficial_resultados.csv")


@dataclass(frozen=True, slots=True)
class RealModelArtifactConfig:
    """Resolve artifact locations while keeping the trusted digest immutable."""

    model_path: Path
    dataset_path: Path
    expected_sha256: str = REAL_MODEL_V1_SHA256

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RealModelArtifactConfig:
        values = os.environ if env is None else env
        return cls(
            model_path=Path(
                values.get("BENTER_REAL_MODEL_PATH", str(DEFAULT_REAL_MODEL_PATH))
            ).expanduser(),
            dataset_path=Path(
                values.get("BENTER_REAL_DATASET_PATH", str(DEFAULT_REAL_DATASET_PATH))
            ).expanduser(),
        )


@dataclass(frozen=True, slots=True)
class EnsembleArtifactConfig:
    model_path: Path
    dataset_path: Path
    expected_sha256: str = ENSEMBLE_MODEL_V1_SHA256

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> EnsembleArtifactConfig:
        values = os.environ if env is None else env
        return cls(
            model_path=Path(
                values.get("BENTER_ENSEMBLE_MODEL_PATH", str(DEFAULT_ENSEMBLE_MODEL_PATH))
            ).expanduser(),
            dataset_path=Path(
                values.get("BENTER_REAL_DATASET_PATH", str(DEFAULT_REAL_DATASET_PATH))
            ).expanduser(),
        )
