"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Engine

from benter_peru.db.engine import create_database_engine
from benter_peru.db.migrations import upgrade_database


@pytest.fixture
def migrated_engine(tmp_path) -> Iterator[Engine]:
    database_path = tmp_path / "benter-test.db"
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    upgrade_database(engine)
    try:
        yield engine
    finally:
        engine.dispose()
