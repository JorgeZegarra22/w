"""End-to-end local history import through the public CLI."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, insert, select

from benter_peru.cli import main
from benter_peru.db.engine import create_database_engine
from benter_peru.db.migrations import upgrade_database
from benter_peru.db.schema import horse_race_results, horses


def test_cli_imports_history_without_network(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    database_path = tmp_path / "history.sqlite3"
    engine = create_database_engine(
        f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"
    )
    upgrade_database(engine)
    horse_id = "01J00000000000000000000401"
    with engine.begin() as connection:
        connection.execute(
            insert(horses).values(
                id=horse_id,
                canonical_name="WAYTT",
                normalized_name="waytt",
                confirmation_status="confirmed",
                created_at=datetime(2026, 11, 18, tzinfo=UTC),
            )
        )
    engine.dispose()
    csv_path = tmp_path / "history.csv"
    csv_path.write_text(
        "horse_id,horse_name,race_date,position,distance_meters,"
        "elapsed_time_seconds,surface,track_condition,meeting_code,race_number\n"
        f"{horse_id},WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3\n",
        encoding="utf-8",
    )
    environment = {
        "BENTER_SOURCE_URL": "https://network-must-not-be-used.invalid/",
        "BENTER_USER_AGENT": "BenterPeruBot/1.0 (+https://github.com/example/hipico)",
        "BENTER_DATABASE_PATH": str(database_path),
        "BENTER_BLOB_ROOT": str(tmp_path / "blobs"),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    exit_code = main(["history", "import", "--file", str(csv_path)])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["rows_inserted"] == 1
    assert report["reused_batch"] is False
    verification_engine = create_database_engine(
        f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"
    )
    with verification_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(horse_race_results)) == 1
    verification_engine.dispose()
