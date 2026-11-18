"""Transactional projection of extracted facts into master entities."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, insert, select
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.sql.schema import Table

from benter_peru.db.schema import (
    document_versions,
    extracted_facts,
    extraction_runs,
    horses,
    jockeys,
    race_entries,
    races,
    studs,
    trainers,
)
from benter_peru.db.uow import UnitOfWork
from benter_peru.entities.models import ResolutionReport
from benter_peru.entities.normalization import best_match, normalize_name
from benter_peru.extraction.identity import EXTRACTOR_NAME, EXTRACTOR_VERSION
from benter_peru.ids import new_ulid

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ResolutionError(ValueError):
    """Raised when extracted facts cannot be projected safely."""


class IdentityAmbiguityError(ResolutionError):
    """Raised when noisy evidence conflicts with a confirmed identity."""


class EntityResolver:
    """Resolve the latest completed extractor-v3 facts for one immutable PDF."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def resolve_sha(self, sha256: str) -> ResolutionReport:
        if _SHA256.fullmatch(sha256) is None:
            raise ResolutionError("sha256 must be 64 lowercase hexadecimal characters")

        counters = {name: 0 for name in asdict(ResolutionReport())}
        with UnitOfWork(self._engine) as uow:
            connection = uow.connection
            extraction = connection.execute(self._extraction_query(sha256)).mappings().first()
            if extraction is None:
                raise ResolutionError(
                    f"no completed {EXTRACTOR_NAME} v{EXTRACTOR_VERSION} extraction for {sha256}"
                )
            fact_rows = connection.execute(
                select(extracted_facts).where(
                    extracted_facts.c.extraction_run_id == extraction["extraction_run_id"]
                )
            ).mappings().all()
            contexts = [row for row in fact_rows if row["fact_type"] == "race_context"]
            if len(contexts) != 1:
                raise ResolutionError("latest extraction must contain exactly one race_context")

            context = self._json_object(contexts[0]["normalized_value"])
            race_id, created = self._resolve_race(
                connection, context, str(extraction["document_version_id"])
            )
            counters["races_created" if created else "races_reused"] += 1

            entries = sorted(
                (row for row in fact_rows if row["fact_type"] == "race_entry"),
                key=lambda row: int(self._json_object(row["normalized_value"])["mandil"]),
            )
            for row in entries:
                if connection.scalar(
                    select(race_entries.c.id).where(
                        race_entries.c.source_fact_id == row["id"]
                    )
                ):
                    counters["entries_reused"] += 1
                    continue
                payload = self._json_object(row["normalized_value"])
                horse_uncertain = bool(row["requires_review"]) or bool(
                    payload.get("horse_requires_review", False)
                )
                horse_id, created = self._resolve_entity(
                    connection,
                    horses,
                    str(payload["horse_name"]),
                    threshold=0.98,
                    uncertain=horse_uncertain,
                )
                counters["horses_created" if created else "horses_reused"] += 1
                jockey_id, created = self._resolve_entity(
                    connection, jockeys, str(payload["jockey"]), threshold=0.94
                )
                counters["jockeys_created" if created else "jockeys_reused"] += 1
                trainer_id, created = self._resolve_entity(
                    connection, trainers, str(payload["trainer"]), threshold=0.94
                )
                counters["trainers_created" if created else "trainers_reused"] += 1
                stud_id, created = self._resolve_entity(
                    connection, studs, str(payload["stud"]), threshold=0.94
                )
                counters["studs_created" if created else "studs_reused"] += 1
                connection.execute(
                    insert(race_entries).values(
                        id=new_ulid(),
                        race_id=race_id,
                        horse_id=horse_id,
                        jockey_id=jockey_id,
                        trainer_id=trainer_id,
                        stud_id=stud_id,
                        source_fact_id=row["id"],
                        mandil=int(payload["mandil"]),
                        weight=Decimal(str(payload["weight"])),
                        created_at=datetime.now(UTC),
                    )
                )
                counters["entries_created"] += 1

            counters["unconfirmed_horses"] = int(
                connection.scalar(
                    select(func.count()).select_from(horses).where(
                        horses.c.confirmation_status == "unconfirmed"
                    )
                )
                or 0
            )
        return ResolutionReport(**counters)

    @staticmethod
    def _extraction_query(sha256: str) -> Select[tuple[Any, ...]]:
        return (
            select(
                extraction_runs.c.id.label("extraction_run_id"),
                extraction_runs.c.document_version_id,
            )
            .join(
                document_versions,
                document_versions.c.id == extraction_runs.c.document_version_id,
            )
            .where(
                document_versions.c.blob_sha256 == sha256,
                extraction_runs.c.extractor_name == EXTRACTOR_NAME,
                extraction_runs.c.extractor_version == EXTRACTOR_VERSION,
                extraction_runs.c.status == "completed",
            )
            .order_by(extraction_runs.c.id.desc())
            .limit(1)
        )

    @staticmethod
    def _json_object(value: object) -> dict[str, Any]:
        parsed = json.loads(str(value))
        if not isinstance(parsed, dict):
            raise ResolutionError("fact normalized_value must be a JSON object")
        return parsed

    @staticmethod
    def _resolve_race(
        connection: Connection,
        context: dict[str, Any],
        document_version_id: str,
    ) -> tuple[str, bool]:
        meeting_code = str(context["meeting_code"])
        race_number = int(context["race_number"])
        values = {
            "scheduled_date": date.fromisoformat(str(context["scheduled_date"])),
            "distance_meters": int(context["distance_meters"]),
            "surface": str(context["surface"]),
        }
        existing = connection.execute(
            select(races).where(
                races.c.meeting_code == meeting_code,
                races.c.race_number == race_number,
            )
        ).mappings().first()
        if existing is not None:
            if any(existing[name] != value for name, value in values.items()):
                raise ResolutionError("race context conflicts with the existing race")
            return str(existing["id"]), False
        race_id = new_ulid()
        connection.execute(
            insert(races).values(
                id=race_id,
                source_document_version_id=document_version_id,
                meeting_code=meeting_code,
                race_number=race_number,
                confirmation_status="confirmed",
                created_at=datetime.now(UTC),
                **values,
            )
        )
        return race_id, True

    @staticmethod
    def _resolve_entity(
        connection: Connection,
        table: Table,
        observed_name: str,
        *,
        threshold: float,
        uncertain: bool = False,
    ) -> tuple[str, bool]:
        normalized = normalize_name(observed_name)
        if not normalized:
            raise ResolutionError(f"empty normalized identity for {table.name}")
        existing = connection.execute(
            select(table).where(table.c.normalized_name == normalized)
        ).mappings().first()
        if existing is not None:
            if uncertain and existing["confirmation_status"] == "confirmed":
                raise IdentityAmbiguityError(
                    f"unconfirmed {table.name} evidence collides with confirmed identity"
                )
            return str(existing["id"]), False

        if not uncertain:
            rows: list[RowMapping] = list(
                connection.execute(
                    select(table.c.id, table.c.normalized_name).where(
                        table.c.confirmation_status == "confirmed"
                    )
                ).mappings()
            )
            match = best_match(
                normalized,
                {str(row["id"]): str(row["normalized_name"]) for row in rows},
                threshold=threshold,
            )
            if match is not None:
                return match.entity_id, False

        entity_id = new_ulid()
        connection.execute(
            insert(table).values(
                id=entity_id,
                canonical_name=observed_name.strip(),
                normalized_name=normalized,
                confirmation_status="unconfirmed" if uncertain else "confirmed",
                created_at=datetime.now(UTC),
            )
        )
        return entity_id, True
