"""Typed history import inputs and reports."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HistoryImportReport:
    batch_id: str
    file_sha256: str
    rows_inserted: int
    reused_batch: bool


@dataclass(frozen=True, slots=True)
class HistoricalResult:
    horse_id: str
    race_date: date
    finishing_position: int
    distance_meters: int
    elapsed_time_seconds: Decimal
    surface: str
    track_condition: str
    meeting_code: str | None
    race_number: int | None
    row_fingerprint: str

