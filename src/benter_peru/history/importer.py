"""Strict, file-atomic CSV history importer."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection, Engine

from benter_peru.db.schema import (
    history_import_batches,
    horse_race_results,
    horses,
)
from benter_peru.db.uow import UnitOfWork
from benter_peru.entities.normalization import normalize_name
from benter_peru.history.errors import HistoryImportError
from benter_peru.history.models import HistoricalResult, HistoryImportReport
from benter_peru.ids import new_ulid

_COLUMNS = {
    "horse_id",
    "horse_name",
    "race_date",
    "position",
    "distance_meters",
    "elapsed_time_seconds",
    "surface",
    "track_condition",
    "meeting_code",
    "race_number",
}
_MILLISECOND = Decimal("0.001")


class HistoryImporter:
    """Validate and persist one complete CSV in a single transaction."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def import_csv(self, path: Path) -> HistoryImportReport:
        content = path.read_bytes()
        file_sha256 = sha256(content).hexdigest()
        with UnitOfWork(self._engine) as uow:
            connection = uow.connection
            existing = connection.execute(
                select(
                    history_import_batches.c.id,
                    history_import_batches.c.file_sha256,
                ).where(history_import_batches.c.file_sha256 == file_sha256)
            ).first()
            if existing is not None:
                return HistoryImportReport(
                    batch_id=str(existing.id),
                    file_sha256=str(existing.file_sha256),
                    rows_inserted=0,
                    reused_batch=True,
                )

            rows = self._parse(connection, content)
            if not rows:
                raise HistoryImportError(None, "file", "contains no data rows")
            self._reject_existing_fingerprints(connection, rows)
            batch_id = new_ulid()
            now = datetime.now(UTC)
            connection.execute(
                insert(history_import_batches).values(
                    id=batch_id,
                    file_sha256=file_sha256,
                    source_filename=path.name,
                    file_format="csv",
                    row_count=len(rows),
                    imported_at=now,
                )
            )
            connection.execute(
                insert(horse_race_results),
                [
                    {
                        "id": new_ulid(),
                        "import_batch_id": batch_id,
                        "created_at": now,
                        **asdict(row),
                    }
                    for row in rows
                ],
            )
        return HistoryImportReport(
            batch_id=batch_id,
            file_sha256=file_sha256,
            rows_inserted=len(rows),
            reused_batch=False,
        )

    def _parse(self, connection: Connection, content: bytes) -> list[HistoricalResult]:
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HistoryImportError(None, "file", "must be UTF-8") from error
        reader = csv.DictReader(StringIO(decoded))
        headers = set(reader.fieldnames or ())
        if headers != _COLUMNS:
            missing = sorted(_COLUMNS - headers)
            unknown = sorted(headers - _COLUMNS)
            reason = f"invalid headers; missing={missing}, unknown={unknown}"
            raise HistoryImportError(1, "header", reason)

        parsed: list[HistoricalResult] = []
        seen: set[str] = set()
        for row_number, raw in enumerate(reader, start=2):
            if all(not (value or "").strip() for value in raw.values()):
                continue
            result = self._parse_row(connection, row_number, raw)
            if result.row_fingerprint in seen:
                raise HistoryImportError(row_number, "row", "duplicate historical result")
            seen.add(result.row_fingerprint)
            parsed.append(result)
        return parsed

    def _parse_row(
        self,
        connection: Connection,
        row_number: int,
        raw: dict[str, str | None],
    ) -> HistoricalResult:
        values = {name: (raw.get(name) or "").strip() for name in _COLUMNS}
        horse_id = self._resolve_horse(
            connection,
            row_number,
            values["horse_id"],
            values["horse_name"],
        )
        race_date = self._date(values["race_date"], row_number)
        position = self._positive_int(values["position"], row_number, "position")
        distance = self._positive_int(
            values["distance_meters"], row_number, "distance_meters"
        )
        elapsed = self._positive_decimal(
            values["elapsed_time_seconds"], row_number, "elapsed_time_seconds"
        )
        surface = normalize_name(values["surface"])
        if surface not in {"arena", "cesped"}:
            raise HistoryImportError(row_number, "surface", "must be arena or cesped")
        track_condition = normalize_name(values["track_condition"])
        if not track_condition or len(track_condition) > 50:
            raise HistoryImportError(
                row_number, "track_condition", "must contain 1 to 50 characters"
            )
        meeting_code = values["meeting_code"] or None
        if meeting_code is not None and len(meeting_code) > 20:
            raise HistoryImportError(row_number, "meeting_code", "maximum length is 20")
        race_number = (
            self._positive_int(values["race_number"], row_number, "race_number")
            if values["race_number"]
            else None
        )
        canonical: dict[str, Any] = {
            "horse_id": horse_id,
            "race_date": race_date.isoformat(),
            "finishing_position": position,
            "distance_meters": distance,
            "elapsed_time_seconds": str(elapsed),
            "surface": surface,
            "track_condition": track_condition,
            "meeting_code": meeting_code,
            "race_number": race_number,
        }
        fingerprint = sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return HistoricalResult(
            horse_id=horse_id,
            race_date=race_date,
            finishing_position=position,
            distance_meters=distance,
            elapsed_time_seconds=elapsed,
            surface=surface,
            track_condition=track_condition,
            meeting_code=meeting_code,
            race_number=race_number,
            row_fingerprint=fingerprint,
        )

    @staticmethod
    def _resolve_horse(
        connection: Connection,
        row_number: int,
        horse_id: str,
        horse_name: str,
    ) -> str:
        if horse_id:
            row = connection.execute(
                select(horses.c.id, horses.c.normalized_name).where(horses.c.id == horse_id)
            ).first()
            if row is None:
                raise HistoryImportError(row_number, "horse_id", "horse not found")
            if horse_name and normalize_name(horse_name) != row.normalized_name:
                raise HistoryImportError(row_number, "horse_name", "contradicts horse_id")
            return str(row.id)
        if not horse_name:
            raise HistoryImportError(
                row_number, "horse_id", "horse_id or horse_name is required"
            )
        matches = connection.execute(
            select(horses.c.id).where(
                horses.c.normalized_name == normalize_name(horse_name),
                horses.c.confirmation_status == "confirmed",
            )
        ).all()
        if len(matches) != 1:
            raise HistoryImportError(
                row_number, "horse_name", "confirmed horse not found"
            )
        return str(matches[0].id)

    @staticmethod
    def _date(value: str, row_number: int) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise HistoryImportError(row_number, "race_date", "invalid ISO date") from error

    @staticmethod
    def _positive_int(value: str, row_number: int, field: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise HistoryImportError(row_number, field, "must be a positive integer") from error
        if parsed <= 0:
            raise HistoryImportError(row_number, field, "must be a positive integer")
        return parsed

    @staticmethod
    def _positive_decimal(value: str, row_number: int, field: str) -> Decimal:
        try:
            parsed = Decimal(value).quantize(_MILLISECOND)
        except InvalidOperation as error:
            raise HistoryImportError(row_number, field, "must be a positive decimal") from error
        if parsed <= 0:
            raise HistoryImportError(row_number, field, "must be a positive decimal")
        return parsed

    @staticmethod
    def _reject_existing_fingerprints(
        connection: Connection, rows: list[HistoricalResult]
    ) -> None:
        fingerprints = [row.row_fingerprint for row in rows]
        existing = connection.scalar(
            select(horse_race_results.c.row_fingerprint).where(
                horse_race_results.c.row_fingerprint.in_(fingerprints)
            )
        )
        if existing is not None:
            raise HistoryImportError(None, "row", "historical result already imported")
