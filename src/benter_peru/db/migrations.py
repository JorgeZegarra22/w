"""Programmatic Alembic entry points used by the application and tests."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def upgrade_database(engine: Engine, revision: str = "head") -> None:
    """Upgrade an existing engine connection to an Alembic revision."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
