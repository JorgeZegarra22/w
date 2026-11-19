"""Materialize official program facts and snapshots in one transaction."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from typing import Any

from sqlalchemy import Connection, Engine, Table, insert, select

from benter_peru.db import schema as db
from benter_peru.db.uow import UnitOfWork
from benter_peru.entities.normalization import normalize_name
from benter_peru.ids import new_ulid
from benter_peru.scrapers.official_scraper import (
    BASE_URL,
    OfficialEntry,
    OfficialProgramError,
    parse_program,
)
from benter_peru.storage.local import LocalBlobStore

type Capture = tuple[str, str, datetime]


def _id(connection: Connection, table: Table, keys: dict[str, Any], **extra: Any) -> str:
    found = connection.scalar(select(table.c.id).filter_by(**keys))
    if found is not None:
        return str(found)
    identifier = new_ulid()
    connection.execute(insert(table).values(id=identifier, **keys, **extra))
    return identifier


def _fact(
    connection: Connection,
    extraction_id: str,
    kind: str,
    subject: str,
    payload: dict[str, Any],
    *,
    requires_review: bool = False,
) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    fingerprint = sha256(f"{extraction_id}:{kind}:{subject}:{text}".encode()).hexdigest()
    return _id(
        connection,
        db.extracted_facts,
        {"fact_fingerprint": fingerprint},
        extraction_run_id=extraction_id,
        fact_type=kind,
        subject_key=subject,
        normalized_value=text,
        raw_value=text,
        confidence=1,
        requires_review=requires_review,
    )


def _entity(
    connection: Connection, table: Table, name: str, now: datetime, *, confirmed: bool = True
) -> str:
    return _id(
        connection,
        table,
        {"normalized_name": normalize_name(name)},
        canonical_name=name,
        confirmation_status="confirmed" if confirmed else "unconfirmed",
        created_at=now,
    )


def _entry_id(
    connection: Connection, race_id: str, entry: OfficialEntry, extraction_id: str, now: datetime
) -> str:
    existing = connection.execute(
        select(db.race_entries.c.id, db.horses.c.normalized_name)
        .join(db.horses, db.horses.c.id == db.race_entries.c.horse_id)
        .where(db.race_entries.c.race_id == race_id, db.race_entries.c.mandil == entry.mandil)
    ).one_or_none()
    if existing is not None:
        if existing.normalized_name != normalize_name(entry.horse_name):
            raise OfficialProgramError(f"identidad conflictiva para mandil {entry.mandil}")
        return str(existing.id)
    fact_id = _fact(
        connection,
        extraction_id,
        "official_race_entry",
        str(entry.mandil),
        {
            "mandil": entry.mandil,
            "horse_name": entry.horse_name,
            "weight": str(entry.weight),
            "jockey": entry.jockey,
            "trainer": entry.trainer,
            "stud": entry.stud,
        },
        requires_review=entry.jockey is None,
    )
    return _id(
        connection,
        db.race_entries,
        {"race_id": race_id, "mandil": entry.mandil},
        horse_id=_entity(connection, db.horses, entry.horse_name, now),
        jockey_id=_entity(
            connection,
            db.jockeys,
            entry.jockey or "Sin jinete declarado",
            now,
            confirmed=entry.jockey is not None,
        ),
        trainer_id=_entity(connection, db.trainers, entry.trainer, now),
        stud_id=_entity(connection, db.studs, entry.stud, now),
        source_fact_id=fact_id,
        weight=entry.weight,
        created_at=now,
    )


def persist_programs(
    engine: Engine, store: LocalBlobStore, captures: Sequence[Capture], race_date: date
) -> tuple[int, int]:
    """Return new race and snapshot counts after validating every capture."""
    programs = [(parse_program(html, url), html, fetched) for url, html, fetched in captures]
    programs = [item for item in programs if item[0].race_date == race_date]
    if not programs:
        raise OfficialProgramError(f"no se encontraron carreras para {race_date}")
    if len({(p.official_meeting, p.race_number) for p, _, _ in programs}) != len(programs):
        raise OfficialProgramError("dos capturas describen la misma carrera oficial")
    new_races = new_snapshots = 0
    now = datetime.now(UTC)
    with UnitOfWork(engine) as uow:
        connection = uow.connection
        source_id = _id(
            connection,
            db.source_registry,
            {"code": "monterrico_oficial"},
            name="Hipódromo de Monterrico",
            base_url=BASE_URL,
            rate_limit_ms=2500,
            enabled=True,
        )
        run_id = _id(
            connection,
            db.crawl_runs,
            {"correlation_id": new_ulid()},
            source_id=source_id,
            status="completed",
            started_at=now,
            finished_at=now,
        )
        for program, html, fetched in programs:
            content = html.encode("utf-8")
            digest = sha256(content).hexdigest()
            blob = store.put_if_absent(BytesIO(content), digest)
            if connection.scalar(select(db.blob_objects.c.sha256).filter_by(sha256=digest)) is None:
                connection.execute(
                    insert(db.blob_objects).values(
                        sha256=digest,
                        byte_size=blob.byte_size,
                        media_type="text/html",
                        storage_key=blob.storage_key,
                        first_stored_at=now,
                        retained_locally=True,
                    )
                )
            document_id = _id(
                connection,
                db.documents,
                {
                    "source_id": source_id,
                    "canonical_url": program.url,
                },
                document_type="programa_oficial_html",
                first_seen_at=fetched,
                last_seen_at=fetched,
            )
            version_id = _id(
                connection,
                db.document_versions,
                {
                    "document_id": document_id,
                    "blob_sha256": digest,
                },
                crawl_run_id=run_id,
                downloaded_at=fetched,
                detected_at=fetched,
                processing_status="extracted",
            )
            extraction_id = _id(
                connection,
                db.extraction_runs,
                {
                    "input_fingerprint": sha256(
                        f"{version_id}:official-html:1".encode()
                    ).hexdigest(),
                },
                document_version_id=version_id,
                extractor_name="official_html",
                extractor_version="1",
                method="text",
                status="completed",
            )
            race_key = {
                "meeting_code": f"{race_date.year}-{program.official_meeting}",
                "race_number": program.race_number,
            }
            existing = connection.execute(select(db.races).filter_by(**race_key)).mappings().first()
            context = {
                "scheduled_date": race_date,
                "surface": program.surface,
                "distance_meters": program.distance_meters,
            }
            if existing is not None and any(
                existing[key] != value for key, value in context.items()
            ):
                raise OfficialProgramError(f"contexto incompatible de la carrera {race_key}")
            race_id = _id(
                connection,
                db.races,
                race_key,
                **context,
                source_document_version_id=version_id,
                confirmation_status="confirmed",
                created_at=now,
            )
            new_races += existing is None
            _fact(
                connection,
                extraction_id,
                "official_race_context",
                str(program.race_number),
                {
                    **race_key,
                    **context,
                    "scheduled_date": race_date.isoformat(),
                    "scheduled_time": program.scheduled_time,
                },
            )
            for entry in program.entries:
                entry_id = _entry_id(connection, race_id, entry, extraction_id, now)
                key = {"race_entry_id": entry_id, "content_hash": digest}
                snapshot_id = select(db.horse_stats_snapshots.c.id).filter_by(**key)
                if connection.scalar(snapshot_id) is None:
                    _id(
                        connection,
                        db.horse_stats_snapshots,
                        key,
                        source_url=program.url,
                        fetched_at=fetched,
                        profile=dict(entry.profile),
                    )
                    new_snapshots += 1
    return new_races, new_snapshots
