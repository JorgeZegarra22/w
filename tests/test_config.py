"""Environment configuration tests for real-source runs."""

from pathlib import Path

import pytest

from benter_peru.config import RuntimeConfig


def test_runtime_config_reads_real_source_and_external_storage_paths(tmp_path: Path) -> None:
    config = RuntimeConfig.from_env(
        {
            "BENTER_SOURCE_URL": "https://elinformativohipico.net/",
            "BENTER_USER_AGENT": "BenterPeruBot/1.0 (+https://github.com/example/hipico)",
            "BENTER_DATABASE_PATH": str(tmp_path / "real.sqlite3"),
            "BENTER_BLOB_ROOT": str(tmp_path / "blobs"),
            "BENTER_MIN_REQUEST_INTERVAL_SECONDS": "3.5",
        }
    )

    assert config.source_url == "https://elinformativohipico.net/"
    assert config.database_path == tmp_path / "real.sqlite3"
    assert config.blob_root == tmp_path / "blobs"
    assert config.min_request_interval_seconds == 3.5
    assert config.database_url.endswith("/real.sqlite3")


def test_runtime_config_rejects_unidentifiable_user_agent(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contact URL"):
        RuntimeConfig.from_env(
            {
                "BENTER_SOURCE_URL": "https://elinformativohipico.net/",
                "BENTER_USER_AGENT": "BenterPeruBot/1.0",
                "BENTER_DATABASE_PATH": str(tmp_path / "real.sqlite3"),
                "BENTER_BLOB_ROOT": str(tmp_path / "blobs"),
            }
        )
