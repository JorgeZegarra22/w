"""Leakage-safe historical performance features."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import horse_race_results, horses


class FeatureError(ValueError):
    """Raised when a feature request cannot be evaluated safely."""


class FeatureVector(TypedDict):
    starts_total: int
    wins_total: int
    win_rate: float
    podium_rate: float
    days_since_last_race: int | None
    distance_starts: int
    distance_wins: int
    distance_win_rate: float
    distance_podium_rate: float
    distance_average_position: float
    surface_starts: int
    surface_wins: int
    surface_win_rate: float
    surface_podium_rate: float
    surface_average_position: float


class FeatureEngine:
    """Calculate deterministic features using only information before a target race."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def for_horse(
        self,
        *,
        horse_id: str,
        race_date: date,
        distance_meters: int,
        surface: str,
        lookback_days: int = 365,
    ) -> FeatureVector:
        if distance_meters <= 0:
            raise FeatureError("distance_meters must be positive")
        if surface not in {"arena", "cesped"}:
            raise FeatureError("surface must be arena or cesped")
        if lookback_days <= 0:
            raise FeatureError("lookback_days must be positive")
        lower_bound = race_date - timedelta(days=lookback_days)
        with self._engine.connect() as connection:
            if connection.scalar(select(horses.c.id).where(horses.c.id == horse_id)) is None:
                raise FeatureError("horse not found")
            rows = connection.execute(
                select(
                    horse_race_results.c.race_date,
                    horse_race_results.c.finishing_position,
                    horse_race_results.c.distance_meters,
                    horse_race_results.c.surface,
                ).where(
                    horse_race_results.c.horse_id == horse_id,
                    horse_race_results.c.race_date >= lower_bound,
                    horse_race_results.c.race_date < race_date,
                )
            ).all()

        positions = [int(row.finishing_position) for row in rows]
        distance_positions = [
            int(row.finishing_position)
            for row in rows
            if row.distance_meters == distance_meters
        ]
        surface_positions = [
            int(row.finishing_position) for row in rows if row.surface == surface
        ]
        distance_values = self._summarize(distance_positions)
        surface_values = self._summarize(surface_positions)
        latest = max((row.race_date for row in rows), default=None)
        return {
            "starts_total": len(positions),
            "wins_total": self._wins(positions),
            "win_rate": self._rate(self._wins(positions), len(positions)),
            "podium_rate": self._rate(self._podiums(positions), len(positions)),
            "days_since_last_race": (race_date - latest).days if latest else None,
            "distance_starts": distance_values[0],
            "distance_wins": distance_values[1],
            "distance_win_rate": distance_values[2],
            "distance_podium_rate": distance_values[3],
            "distance_average_position": distance_values[4],
            "surface_starts": surface_values[0],
            "surface_wins": surface_values[1],
            "surface_win_rate": surface_values[2],
            "surface_podium_rate": surface_values[3],
            "surface_average_position": surface_values[4],
        }

    @classmethod
    def _summarize(cls, positions: list[int]) -> tuple[int, int, float, float, float]:
        starts = len(positions)
        wins = cls._wins(positions)
        average = round(sum(positions) / starts, 6) if starts else 0.0
        return (
            starts,
            wins,
            cls._rate(wins, starts),
            cls._rate(cls._podiums(positions), starts),
            average,
        )

    @staticmethod
    def _wins(positions: list[int]) -> int:
        return sum(position == 1 for position in positions)

    @staticmethod
    def _podiums(positions: list[int]) -> int:
        return sum(position <= 3 for position in positions)

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 0.0
