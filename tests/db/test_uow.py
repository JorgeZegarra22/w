"""Transaction-boundary tests for the Unit of Work."""

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import source_registry
from benter_peru.db.uow import UnitOfWork


def _source_values() -> dict[str, object]:
    return {
        "id": "01J00000000000000000000000",
        "code": "informativo",
        "name": "El Informativo Hipico",
        "base_url": "https://example.test",
        "rate_limit_ms": 0,
        "enabled": True,
    }


def _source_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.scalar(select(func.count()).select_from(source_registry)) or 0)


def test_unit_of_work_commits_on_clean_exit(migrated_engine: Engine) -> None:
    with UnitOfWork(migrated_engine) as uow:
        uow.connection.execute(insert(source_registry).values(**_source_values()))

    assert _source_count(migrated_engine) == 1


def test_unit_of_work_rolls_back_every_write_on_exception(migrated_engine: Engine) -> None:
    with (
        pytest.raises(RuntimeError, match="pipeline failed"),
        UnitOfWork(migrated_engine) as uow,
    ):
        uow.connection.execute(insert(source_registry).values(**_source_values()))
        raise RuntimeError("pipeline failed")

    assert _source_count(migrated_engine) == 0
