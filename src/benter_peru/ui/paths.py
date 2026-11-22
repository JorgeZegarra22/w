"""Resolve dashboard files relative to the project checkout."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def project_path(path: str | Path) -> Path:
    return PROJECT_ROOT / Path(path).expanduser()
