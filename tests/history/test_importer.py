"""Strict, atomic historical CSV ingestion tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import (
    history_import_batches,
    horse_race_results,
    horses,
)
from benter_peru.history.errors import HistoryImportError
from benter_peru.history.importer import HistoryImporter

WAYTT_ID = "01J00000000000000000000101"
DRUIDA_ID = "01J00000000000000000000102"
NOISY_ID = "01J00000000000000000000103"
HEADER = (
    "horse_id,horse_name,race_date,position,distance_meters,"
    "elapsed_time_seconds,surface,track_condition,meeting_code,race_number\n"
)


def _seed_horses(engine: Engine) -> None:
    now = datetime(2026, 11, 18, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(horses),
            [
                {
                    "id": WAYTT_ID,
                    "canonical_name": "WAYTT",
                    "normalized_name": "waytt",
                    "confirmation_status": "confirmed",
                    "created_at": now,
                },
                {
                    "id": DRUIDA_ID,
                    "canonical_name": "GRAN DRUIDA (USA)",
                    "normalized_name": "gran druida usa",
                    "confirmation_status": "confirmed",
                    "created_at": now,
                },
                {
                    "id": NOISY_ID,
                    "canonical_name": "tNrzrAMo (usA)",
                    "normalized_name": "tnrzramo usa",
                    "confirmation_status": "unconfirmed",
                    "created_at": now,
                },
            ],
        )


def _write(path: Path, *rows: str) -> Path:
    path.write_text(HEADER + "".join(f"{row}\n" for row in rows), encoding="utf-8")
    return path


def test_imports_id_and_exact_confirmed_name_atomically(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _seed_horses(migrated_engine)
    path = _write(
        tmp_path / "history.csv",
        f"{WAYTT_ID},WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3",
        ",gran-druida usa,2026-09-19,3,2400,151.125,cesped,normal,202638,5",
    )

    report = HistoryImporter(migrated_engine).import_csv(path)

    assert report.rows_inserted == 2
    assert report.reused_batch is False
    with migrated_engine.connect() as connection:
        rows = connection.execute(
            select(
                horse_race_results.c.horse_id,
                horse_race_results.c.elapsed_time_seconds,
            ).order_by(horse_race_results.c.race_date.desc())
        ).all()
    assert rows[0][0] == WAYTT_ID
    assert str(rows[0][1]) == "58.940"
    assert rows[1][0] == DRUIDA_ID


def test_contradictory_name_for_authoritative_id_rolls_back(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _seed_horses(migrated_engine)
    path = _write(
        tmp_path / "contradiction.csv",
        f"{WAYTT_ID},WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3",
        f"{WAYTT_ID},GRAN DRUIDA USA,2026-09-19,3,2400,151.125,cesped,normal,202638,5",
    )

    with pytest.raises(HistoryImportError, match="row 3, horse_name: contradicts horse_id"):
        HistoryImporter(migrated_engine).import_csv(path)

    with migrated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(history_import_batches)) == 0
        assert connection.scalar(select(func.count()).select_from(horse_race_results)) == 0


@pytest.mark.parametrize(
    ("horse_id", "horse_name", "message"),
    [
        ("01J00000000000000000000999", "", "horse_id: horse not found"),
        ("", "tNrzrAMo (usA)", "horse_name: confirmed horse not found"),
        ("", "UNKNOWN", "horse_name: confirmed horse not found"),
        ("", "", "horse_id: horse_id or horse_name is required"),
    ],
)
def test_rejects_unsafe_identity(
    migrated_engine: Engine,
    tmp_path: Path,
    horse_id: str,
    horse_name: str,
    message: str,
) -> None:
    _seed_horses(migrated_engine)
    path = _write(
        tmp_path / "unsafe.csv",
        f"{horse_id},{horse_name},2026-10-24,1,1000,58.940,arena,seca,202643,3",
    )

    with pytest.raises(HistoryImportError, match=message):
        HistoryImporter(migrated_engine).import_csv(path)


def test_invalid_later_row_rolls_back_complete_file(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _seed_horses(migrated_engine)
    path = _write(
        tmp_path / "invalid.csv",
        f"{WAYTT_ID},WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3",
        f"{DRUIDA_ID},GRAN DRUIDA USA,not-a-date,3,2400,151.125,cesped,normal,202638,5",
    )

    with pytest.raises(HistoryImportError, match="row 3, race_date: invalid ISO date"):
        HistoryImporter(migrated_engine).import_csv(path)

    with migrated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(history_import_batches)) == 0
        assert connection.scalar(select(func.count()).select_from(horse_race_results)) == 0


def test_reimporting_identical_file_reuses_batch(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _seed_horses(migrated_engine)
    path = _write(
        tmp_path / "same.csv",
        f"{WAYTT_ID},WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3",
    )
    importer = HistoryImporter(migrated_engine)

    first = importer.import_csv(path)
    second = importer.import_csv(path)

    assert second.batch_id == first.batch_id
    assert second.rows_inserted == 0
    assert second.reused_batch is True
    with migrated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(horse_race_results)) == 1


def test_different_file_with_existing_result_rolls_back_new_batch(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _seed_horses(migrated_engine)
    row = f"{WAYTT_ID},WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3"
    first = _write(tmp_path / "first.csv", row)
    second = tmp_path / "second.csv"
    second.write_text(HEADER + row + "\n\n", encoding="utf-8")
    importer = HistoryImporter(migrated_engine)
    importer.import_csv(first)

    with pytest.raises(HistoryImportError, match="historical result already imported"):
        importer.import_csv(second)

    with migrated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(history_import_batches)) == 1
        assert connection.scalar(select(func.count()).select_from(horse_race_results)) == 1
