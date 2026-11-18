"""Leakage-safe horse feature calculations."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import insert
from sqlalchemy.engine import Engine

from benter_peru.db.schema import history_import_batches, horse_race_results, horses
from benter_peru.ml.features import FeatureEngine, FeatureError

HORSE_ID = "01J00000000000000000000201"
EMPTY_HORSE_ID = "01J00000000000000000000202"
BATCH_ID = "01J00000000000000000000203"


def _seed(engine: Engine, results: list[tuple[date, int, int, str]]) -> None:
    now = datetime(2026, 11, 18, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(horses),
            [
                {
                    "id": HORSE_ID,
                    "canonical_name": "WAYTT",
                    "normalized_name": "waytt",
                    "confirmation_status": "confirmed",
                    "created_at": now,
                },
                {
                    "id": EMPTY_HORSE_ID,
                    "canonical_name": "NO HISTORY",
                    "normalized_name": "no history",
                    "confirmation_status": "confirmed",
                    "created_at": now,
                },
            ],
        )
        connection.execute(
            insert(history_import_batches).values(
                id=BATCH_ID,
                file_sha256="a" * 64,
                source_filename="synthetic.csv",
                file_format="csv",
                row_count=max(1, len(results)),
                imported_at=now,
            )
        )
        if results:
            connection.execute(
                insert(horse_race_results),
                [
                {
                    "id": f"01J{300 + index:023d}",
                    "import_batch_id": BATCH_ID,
                    "horse_id": HORSE_ID,
                    "race_date": race_date,
                    "finishing_position": position,
                    "distance_meters": distance,
                    "elapsed_time_seconds": Decimal("60.000"),
                    "surface": surface,
                    "track_condition": "seca",
                    "meeting_code": f"M{index}",
                    "race_number": 1,
                    "row_fingerprint": f"{index + 1:064x}",
                    "created_at": now,
                }
                for index, (race_date, position, distance, surface) in enumerate(results)
                ],
            )


def test_calculates_global_distance_and_surface_features(
    migrated_engine: Engine,
) -> None:
    _seed(
        migrated_engine,
        [
            (date(2026, 10, 24), 1, 1000, "arena"),
            (date(2026, 9, 19), 1, 2400, "arena"),
            (date(2026, 8, 1), 3, 1000, "arena"),
        ],
    )

    features = FeatureEngine(migrated_engine).for_horse(
        horse_id=HORSE_ID,
        race_date=date(2026, 11, 21),
        distance_meters=1000,
        surface="arena",
    )

    assert features == {
        "starts_total": 3,
        "wins_total": 2,
        "win_rate": 0.666667,
        "podium_rate": 1.0,
        "days_since_last_race": 28,
        "distance_starts": 2,
        "distance_wins": 1,
        "distance_win_rate": 0.5,
        "distance_podium_rate": 1.0,
        "distance_average_position": 2.0,
        "surface_starts": 3,
        "surface_wins": 2,
        "surface_win_rate": 0.666667,
        "surface_podium_rate": 1.0,
        "surface_average_position": 1.666667,
    }


def test_excludes_old_same_day_and_future_results(migrated_engine: Engine) -> None:
    _seed(
        migrated_engine,
        [
            (date(2025, 11, 20), 1, 1000, "arena"),
            (date(2025, 11, 21), 3, 1000, "arena"),
            (date(2026, 11, 21), 1, 1000, "arena"),
            (date(2026, 11, 22), 1, 1000, "arena"),
        ],
    )

    features = FeatureEngine(migrated_engine).for_horse(
        horse_id=HORSE_ID,
        race_date=date(2026, 11, 21),
        distance_meters=1000,
        surface="arena",
    )

    assert features["starts_total"] == 1
    assert features["wins_total"] == 0
    assert features["podium_rate"] == 1.0
    assert features["days_since_last_race"] == 365


def test_horse_without_history_returns_zero_vector(migrated_engine: Engine) -> None:
    _seed(migrated_engine, [(date(2026, 10, 24), 1, 1000, "arena")])

    features = FeatureEngine(migrated_engine).for_horse(
        horse_id=EMPTY_HORSE_ID,
        race_date=date(2026, 11, 21),
        distance_meters=2400,
        surface="cesped",
    )

    assert features["starts_total"] == 0
    assert features["win_rate"] == 0.0
    assert features["distance_average_position"] == 0.0
    assert features["surface_average_position"] == 0.0
    assert features["days_since_last_race"] is None


@pytest.mark.parametrize(
    ("horse_id", "distance", "surface", "lookback", "message"),
    [
        ("01J00000000000000000000999", 1000, "arena", 365, "horse not found"),
        (HORSE_ID, 0, "arena", 365, "distance_meters must be positive"),
        (HORSE_ID, 1000, "barro", 365, "surface must be arena or cesped"),
        (HORSE_ID, 1000, "arena", 0, "lookback_days must be positive"),
    ],
)
def test_rejects_invalid_feature_request(
    migrated_engine: Engine,
    horse_id: str,
    distance: int,
    surface: str,
    lookback: int,
    message: str,
) -> None:
    _seed(migrated_engine, [])

    with pytest.raises(FeatureError, match=message):
        FeatureEngine(migrated_engine).for_horse(
            horse_id=horse_id,
            race_date=date(2026, 11, 21),
            distance_meters=distance,
            surface=surface,
            lookback_days=lookback,
        )
