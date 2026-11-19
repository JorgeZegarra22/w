"""Read-only dashboard database query tests."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from benter_peru.ui.queries import (
    DATABASE_ERROR_MESSAGE,
    DashboardDatabaseError,
    DashboardRepository,
)


def _create_dashboard_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE horses (
                id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL
            );
            CREATE TABLE jockeys (
                id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL
            );
            CREATE TABLE trainers (
                id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL
            );
            CREATE TABLE studs (
                id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL
            );
            CREATE TABLE races (
                id TEXT PRIMARY KEY,
                meeting_code TEXT NOT NULL,
                race_number INTEGER NOT NULL,
                scheduled_date DATE NOT NULL,
                distance_meters INTEGER NOT NULL,
                surface TEXT NOT NULL
            );
            CREATE TABLE race_entries (
                id TEXT PRIMARY KEY,
                race_id TEXT NOT NULL,
                horse_id TEXT NOT NULL,
                jockey_id TEXT NOT NULL,
                trainer_id TEXT NOT NULL,
                stud_id TEXT NOT NULL,
                mandil INTEGER NOT NULL,
                weight NUMERIC NOT NULL
            );
            CREATE TABLE extracted_facts (id TEXT PRIMARY KEY);
            CREATE TABLE horse_race_results (
                id TEXT PRIMARY KEY,
                horse_id TEXT NOT NULL,
                race_date DATE NOT NULL,
                finishing_position INTEGER NOT NULL,
                distance_meters INTEGER NOT NULL,
                surface TEXT NOT NULL
            );
            CREATE TABLE journalist_picks (
                id TEXT PRIMARY KEY,
                meeting_code TEXT NOT NULL,
                race_number INTEGER NOT NULL,
                selection_rank INTEGER NOT NULL,
                mandil INTEGER,
                horse_name_raw TEXT NOT NULL,
                journalist_name TEXT NOT NULL,
                confidence NUMERIC NOT NULL,
                requires_review BOOLEAN NOT NULL
            );

            INSERT INTO horses VALUES ('horse-1', 'WAYTT');
            INSERT INTO horses VALUES ('horse-2', 'REFUGIADO');
            INSERT INTO jockeys VALUES ('jockey-1', 'J H SUAREZ');
            INSERT INTO trainers VALUES ('trainer-1', 'R MELGAREJO');
            INSERT INTO studs VALUES ('stud-1', 'S.B.P.');
            INSERT INTO races VALUES (
                'race-1', '202647', 1, '2026-11-21', 1000, 'arena'
            );
            INSERT INTO race_entries VALUES (
                'entry-1', 'race-1', 'horse-1', 'jockey-1', 'trainer-1',
                'stud-1', 1, 56
            );
            INSERT INTO race_entries VALUES (
                'entry-2', 'race-1', 'horse-2', 'jockey-1', 'trainer-1',
                'stud-1', 2, 54.5
            );
            INSERT INTO extracted_facts VALUES ('fact-1');
            INSERT INTO extracted_facts VALUES ('fact-2');
            INSERT INTO extracted_facts VALUES ('fact-3');
            INSERT INTO horse_race_results VALUES (
                'result-1', 'horse-1', '2026-10-24', 1, 1000, 'arena'
            );
            INSERT INTO horse_race_results VALUES (
                'result-2', 'horse-2', '2026-10-24', 3, 1000, 'arena'
            );
            INSERT INTO journalist_picks VALUES (
                'pick-1', '202647', 1, 1, 1, 'WAYTT',
                'ESTUDIE SU POLLA', 0.97, 0
            );
            INSERT INTO journalist_picks VALUES (
                'pick-2', '202647', 1, 2, NULL, 'REFUGIADO?',
                'ESTUDIE SU POLLA', 0.55, 1
            );
            """
        )


def test_missing_database_raises_friendly_error(tmp_path: Path) -> None:
    with pytest.raises(DashboardDatabaseError, match=DATABASE_ERROR_MESSAGE):
        DashboardRepository.open(tmp_path / "missing.sqlite3")


def test_stale_schema_raises_friendly_error(tmp_path: Path) -> None:
    database_path = tmp_path / "stale.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE horses (id TEXT PRIMARY KEY)")

    with pytest.raises(DashboardDatabaseError, match=DATABASE_ERROR_MESSAGE):
        DashboardRepository.open(database_path)


def test_schema_without_historical_results_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "pre-history.sqlite3"
    _create_dashboard_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TABLE horse_race_results")

    with pytest.raises(DashboardDatabaseError, match=DATABASE_ERROR_MESSAGE):
        DashboardRepository.open(database_path)


def test_repository_connection_is_sqlite_read_only(tmp_path: Path) -> None:
    database_path = tmp_path / "dashboard.sqlite3"
    _create_dashboard_database(database_path)
    repository = DashboardRepository.open(database_path)
    try:
        with (
            repository.engine.begin() as connection,
            pytest.raises(OperationalError, match="readonly"),
        ):
            connection.execute(
                text("INSERT INTO horses (id, canonical_name) VALUES ('x', 'X')")
            )
    finally:
        repository.close()


def test_summary_and_race_queries_return_typed_projections(tmp_path: Path) -> None:
    database_path = tmp_path / "dashboard.sqlite3"
    _create_dashboard_database(database_path)
    repository = DashboardRepository.open(database_path)
    try:
        assert repository.summary().horses_total == 2
        assert repository.summary().races_total == 1
        assert repository.summary().facts_total == 3
        assert repository.meeting_codes() == ("202647",)

        races = repository.races_for_meeting("202647")
        assert len(races) == 1
        assert races[0].race_number == 1
        assert races[0].scheduled_date == date(2026, 11, 21)
        assert races[0].distance_meters == 1000
        assert races[0].surface == "arena"
        assert repository.races_on_date(date(2026, 11, 21)) == races

        participants = repository.participants_for_race("race-1")
        assert [participant.mandil for participant in participants] == [1, 2]
        assert participants[0].horse_name == "WAYTT"
        assert participants[0].jockey_name == "J H SUAREZ"
        assert participants[0].trainer_name == "R MELGAREJO"
        assert participants[0].stud_name == "S.B.P."
        assert participants[1].weight == 54.5
        picks = repository.journalist_picks_for_race("202647", 1)
        assert picks[0].mandil == 1
        assert picks[0].requires_review is False
        assert picks[1].horse_name_raw == "REFUGIADO?"
        assert picks[1].requires_review is True
    finally:
        repository.close()


def test_latest_snapshot_is_selected_per_entry(tmp_path: Path) -> None:
    database_path = tmp_path / "snapshots.sqlite3"
    _create_dashboard_database(database_path)
    repository = DashboardRepository.open(database_path)
    try:
        assert repository.horse_snapshots_for_race("race-1") == {}
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE horse_stats_snapshots (
                    race_entry_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    fetched_at DATETIME NOT NULL,
                    content_hash TEXT NOT NULL,
                    profile JSON NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT INTO horse_stats_snapshots VALUES (?, ?, ?, ?, ?)",
                [
                    ("entry-1", "https://example.test/old", "2026-11-18 12:00:00",
                     "a" * 64, '{"recent_races": []}'),
                    ("entry-1", "https://example.test/new", "2026-11-19 12:00:00",
                     "b" * 64, '{"recent_races": [{"date": "2026-10-24", "position": 2}]}'),
                ],
            )
        snapshots = repository.horse_snapshots_for_race("race-1")
        assert set(snapshots) == {1}
        assert snapshots[1].source_url == "https://example.test/new"
        assert snapshots[1].profile["recent_races"] == [{"date": "2026-10-24", "position": 2}]
        assert repository.horse_snapshots_for_race("other-race") == {}
    finally:
        repository.close()
