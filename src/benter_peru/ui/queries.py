"""Framework-free, read-only projections for the Streamlit dashboard."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from benter_peru.db.schema import (
    extracted_facts,
    horses,
    jockeys,
    journalist_picks,
    race_entries,
    races,
    studs,
    trainers,
)

DATABASE_ERROR_MESSAGE = (
    "Base de datos no encontrada o esquema desactualizado. "
    "Por favor, ejecute las migraciones y el pipeline de ingesta primero"
)

_REQUIRED_TABLES = frozenset(
    {
        "extracted_facts",
        "horse_race_results",
        "horses",
        "journalist_picks",
        "jockeys",
        "race_entries",
        "races",
        "studs",
        "trainers",
    }
)


class DashboardDatabaseError(RuntimeError):
    """Raised when the dashboard cannot safely read its expected database."""


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    horses_total: int
    races_total: int
    facts_total: int


@dataclass(frozen=True, slots=True)
class RaceOption:
    id: str
    meeting_code: str
    race_number: int
    scheduled_date: date
    distance_meters: int
    surface: str


@dataclass(frozen=True, slots=True)
class RaceParticipant:
    horse_id: str
    mandil: int
    horse_name: str
    jockey_name: str
    trainer_name: str
    stud_name: str
    weight: float


@dataclass(frozen=True, slots=True)
class JournalistPick:
    selection_rank: int
    mandil: int | None
    horse_name_raw: str
    journalist_name: str
    confidence: float
    requires_review: bool


class DashboardRepository:
    """Expose dashboard projections over an immutable SQLite connection."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def open(cls, database_path: Path) -> DashboardRepository:
        path = database_path.expanduser().resolve()
        if not path.is_file():
            raise DashboardDatabaseError(DATABASE_ERROR_MESSAGE)
        quoted_path = quote(path.as_posix(), safe="/:")
        sqlite_uri = f"file:{quoted_path}?mode=ro"
        engine = create_engine(
            "sqlite+pysqlite://",
            creator=lambda: sqlite3.connect(
                sqlite_uri, uri=True, check_same_thread=False
            ),
        )
        try:
            actual_tables = frozenset(inspect(engine).get_table_names())
            if not _REQUIRED_TABLES.issubset(actual_tables):
                raise DashboardDatabaseError(DATABASE_ERROR_MESSAGE)
        except DashboardDatabaseError:
            engine.dispose()
            raise
        except SQLAlchemyError as error:
            engine.dispose()
            raise DashboardDatabaseError(DATABASE_ERROR_MESSAGE) from error
        return cls(engine)

    def close(self) -> None:
        self.engine.dispose()

    def summary(self) -> DashboardSummary:
        with self.engine.connect() as connection:
            return DashboardSummary(
                horses_total=int(
                    connection.scalar(select(func.count()).select_from(horses)) or 0
                ),
                races_total=int(
                    connection.scalar(select(func.count()).select_from(races)) or 0
                ),
                facts_total=int(
                    connection.scalar(select(func.count()).select_from(extracted_facts)) or 0
                ),
            )

    def meeting_codes(self) -> tuple[str, ...]:
        statement = select(races.c.meeting_code).distinct().order_by(races.c.meeting_code)
        with self.engine.connect() as connection:
            return tuple(str(row.meeting_code) for row in connection.execute(statement))

    def races_for_meeting(self, meeting_code: str) -> tuple[RaceOption, ...]:
        statement = (
            select(
                races.c.id,
                races.c.meeting_code,
                races.c.race_number,
                races.c.scheduled_date,
                races.c.distance_meters,
                races.c.surface,
            )
            .where(races.c.meeting_code == meeting_code)
            .order_by(races.c.race_number)
        )
        with self.engine.connect() as connection:
            return tuple(
                RaceOption(
                    id=str(row.id),
                    meeting_code=str(row.meeting_code),
                    race_number=int(row.race_number),
                    scheduled_date=row.scheduled_date,
                    distance_meters=int(row.distance_meters),
                    surface=str(row.surface),
                )
                for row in connection.execute(statement)
            )

    def races_on_date(self, scheduled_date: date) -> tuple[RaceOption, ...]:
        statement = (
            select(
                races.c.id,
                races.c.meeting_code,
                races.c.race_number,
                races.c.scheduled_date,
                races.c.distance_meters,
                races.c.surface,
            )
            .where(races.c.scheduled_date == scheduled_date)
            .order_by(races.c.meeting_code, races.c.race_number)
        )
        with self.engine.connect() as connection:
            return tuple(
                RaceOption(
                    id=str(row.id),
                    meeting_code=str(row.meeting_code),
                    race_number=int(row.race_number),
                    scheduled_date=row.scheduled_date,
                    distance_meters=int(row.distance_meters),
                    surface=str(row.surface),
                )
                for row in connection.execute(statement)
            )

    def participants_for_race(self, race_id: str) -> tuple[RaceParticipant, ...]:
        statement = (
            select(
                race_entries.c.horse_id,
                race_entries.c.mandil,
                horses.c.canonical_name.label("horse_name"),
                jockeys.c.canonical_name.label("jockey_name"),
                trainers.c.canonical_name.label("trainer_name"),
                studs.c.canonical_name.label("stud_name"),
                race_entries.c.weight,
            )
            .join(horses, horses.c.id == race_entries.c.horse_id)
            .join(jockeys, jockeys.c.id == race_entries.c.jockey_id)
            .join(trainers, trainers.c.id == race_entries.c.trainer_id)
            .join(studs, studs.c.id == race_entries.c.stud_id)
            .where(race_entries.c.race_id == race_id)
            .order_by(race_entries.c.mandil)
        )
        with self.engine.connect() as connection:
            return tuple(
                RaceParticipant(
                    horse_id=str(row.horse_id),
                    mandil=int(row.mandil),
                    horse_name=str(row.horse_name),
                    jockey_name=str(row.jockey_name),
                    trainer_name=str(row.trainer_name),
                    stud_name=str(row.stud_name),
                    weight=float(row.weight),
                )
                for row in connection.execute(statement)
            )

    def journalist_picks_for_race(
        self, meeting_code: str, race_number: int
    ) -> tuple[JournalistPick, ...]:
        statement = (
            select(
                journalist_picks.c.selection_rank,
                journalist_picks.c.mandil,
                journalist_picks.c.horse_name_raw,
                journalist_picks.c.journalist_name,
                journalist_picks.c.confidence,
                journalist_picks.c.requires_review,
            )
            .where(
                journalist_picks.c.meeting_code == meeting_code,
                journalist_picks.c.race_number == race_number,
            )
            .order_by(journalist_picks.c.selection_rank)
        )
        with self.engine.connect() as connection:
            return tuple(
                JournalistPick(
                    selection_rank=int(row.selection_rank),
                    mandil=None if row.mandil is None else int(row.mandil),
                    horse_name_raw=str(row.horse_name_raw),
                    journalist_name=str(row.journalist_name),
                    confidence=float(row.confidence),
                    requires_review=bool(row.requires_review),
                )
                for row in connection.execute(statement)
            )
