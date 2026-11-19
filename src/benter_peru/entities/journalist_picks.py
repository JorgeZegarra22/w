"""Transactional materialization of journalist-pick extraction facts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import (
    document_versions,
    extracted_facts,
    extraction_runs,
    journalist_picks,
)
from benter_peru.db.uow import UnitOfWork
from benter_peru.extraction.identity import EXTRACTOR_NAME, EXTRACTOR_VERSION
from benter_peru.ids import new_ulid

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class JournalistPickResolutionError(ValueError):
    """Raised when magazine facts cannot be materialized safely."""


@dataclass(frozen=True, slots=True)
class JournalistPickReport:
    created: int = 0
    reused: int = 0
    requires_review: int = 0


class JournalistPickResolver:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def resolve_sha(self, sha256: str) -> JournalistPickReport:
        if _SHA256.fullmatch(sha256) is None:
            raise JournalistPickResolutionError("invalid sha256")
        created = reused = review_count = 0
        with UnitOfWork(self._engine) as uow:
            connection = uow.connection
            extraction = connection.execute(
                select(
                    extraction_runs.c.id,
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
            ).mappings().first()
            if extraction is None:
                raise JournalistPickResolutionError("no completed magazine extraction")
            facts = connection.execute(
                select(extracted_facts).where(
                    extracted_facts.c.extraction_run_id == extraction["id"],
                    extracted_facts.c.fact_type == "journalist_pick",
                )
            ).mappings().all()
            if not facts:
                raise JournalistPickResolutionError("extraction has no journalist picks")
            for fact in facts:
                existing = connection.scalar(
                    select(journalist_picks.c.id).where(
                        journalist_picks.c.source_fact_id == fact["id"]
                    )
                )
                if existing is not None:
                    reused += 1
                    if bool(fact["requires_review"]):
                        review_count += 1
                    continue
                payload = self._payload(fact["normalized_value"])
                mandil_raw = payload.get("mandil")
                mandil = None if mandil_raw is None else int(mandil_raw)
                connection.execute(
                    insert(journalist_picks).values(
                        id=new_ulid(),
                        source_document_version_id=extraction["document_version_id"],
                        source_fact_id=fact["id"],
                        meeting_code=str(payload["meeting_code"]),
                        race_number=int(payload["race_number"]),
                        selection_rank=int(payload["rank"]),
                        mandil=mandil,
                        horse_name_raw=str(payload["horse_name"]),
                        journalist_name=str(payload["journalist"]),
                        confidence=Decimal(str(fact["confidence"])),
                        requires_review=bool(fact["requires_review"]),
                        created_at=datetime.now(UTC),
                    )
                )
                created += 1
                if bool(fact["requires_review"]):
                    review_count += 1
        return JournalistPickReport(created, reused, review_count)

    @staticmethod
    def _payload(value: object) -> dict[str, Any]:
        parsed = json.loads(str(value))
        required = {
            "meeting_code",
            "race_number",
            "rank",
            "mandil",
            "horse_name",
            "journalist",
        }
        if not isinstance(parsed, dict) or set(parsed) != required:
            raise JournalistPickResolutionError("invalid journalist pick payload")
        if not str(parsed["horse_name"]).strip() or not str(parsed["journalist"]).strip():
            raise JournalistPickResolutionError("empty journalist pick identity")
        if int(parsed["race_number"]) <= 0 or int(parsed["rank"]) <= 0:
            raise JournalistPickResolutionError("invalid journalist pick position")
        return parsed
