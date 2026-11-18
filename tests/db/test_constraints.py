from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Connection, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from benter_peru.db.schema import (
    blob_objects,
    crawl_runs,
    document_versions,
    documents,
    extracted_facts,
    extraction_runs,
    fact_evidence,
    history_import_batches,
    horse_race_results,
    horses,
    jockeys,
    processing_tasks,
    race_entries,
    races,
    run_reports,
    source_registry,
    studs,
    trainers,
)

SOURCE_ID = "01J00000000000000000000000"
RUN_ID = "01J00000000000000000000001"
DOCUMENT_ID = "01J00000000000000000000002"
DOCUMENT_VERSION_ID = "01J00000000000000000000003"
EXTRACTION_RUN_ID = "01J00000000000000000000004"
FACT_ID = "01J00000000000000000000005"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
OBSERVED_AT = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def seeded_connection(migrated_engine: Engine) -> Iterator[Connection]:
    with migrated_engine.begin() as connection:
        connection.execute(
            insert(source_registry).values(
                id=SOURCE_ID,
                code="el-informativo",
                name="El Informativo Hipico",
                base_url="https://example.invalid/",
                rate_limit_ms=2000,
                enabled=True,
            )
        )
        connection.execute(
            insert(crawl_runs).values(
                id=RUN_ID,
                source_id=SOURCE_ID,
                correlation_id="run-001",
                status="running",
                started_at=OBSERVED_AT,
            )
        )
        connection.execute(
            insert(blob_objects).values(
                sha256=SHA256_A,
                byte_size=128,
                media_type="application/pdf",
                storage_key=f"sha256/{SHA256_A}",
                first_stored_at=OBSERVED_AT,
                retained_locally=True,
            )
        )
        connection.execute(
            insert(documents).values(
                id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                canonical_url="https://example.invalid/document.pdf",
                document_type="estudie_su_polla",
                first_seen_at=OBSERVED_AT,
                last_seen_at=OBSERVED_AT,
            )
        )
        connection.execute(
            insert(document_versions).values(
                id=DOCUMENT_VERSION_ID,
                document_id=DOCUMENT_ID,
                blob_sha256=SHA256_A,
                crawl_run_id=RUN_ID,
                detected_at=OBSERVED_AT,
                downloaded_at=OBSERVED_AT,
                processing_status="pending",
            )
        )
        yield connection


def test_foreign_key_rejects_unknown_source(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(
            insert(crawl_runs).values(
                id="01J00000000000000000000010",
                source_id="01J99999999999999999999999",
                correlation_id="orphan-run",
                status="running",
                started_at=OBSERVED_AT,
            )
        )


def test_blob_sha256_is_physically_unique(seeded_connection: Connection) -> None:
    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(blob_objects).values(
                sha256=SHA256_A,
                byte_size=999,
                media_type="application/pdf",
                storage_key="sha256/duplicate",
                first_stored_at=OBSERVED_AT,
                retained_locally=True,
            )
        )


def test_processing_task_idempotency_key_is_unique(seeded_connection: Connection) -> None:
    values = {
        "crawl_run_id": RUN_ID,
        "document_version_id": DOCUMENT_VERSION_ID,
        "idempotency_key": SHA256_B,
        "task_type": "extract",
        "status": "pending",
        "attempt_count": 0,
    }
    seeded_connection.execute(
        insert(processing_tasks).values(id="01J00000000000000000000011", **values)
    )

    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(processing_tasks).values(id="01J00000000000000000000012", **values)
        )


def test_document_version_content_pair_is_unique(seeded_connection: Connection) -> None:
    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(document_versions).values(
                id="01J00000000000000000000013",
                document_id=DOCUMENT_ID,
                blob_sha256=SHA256_A,
                crawl_run_id=RUN_ID,
                detected_at=OBSERVED_AT,
                processing_status="pending",
            )
        )


def test_run_report_is_unique_per_crawl_run(seeded_connection: Connection) -> None:
    counts = {
        "status": "completed",
        "discovered_count": 1,
        "downloaded_count": 1,
        "deduplicated_count": 0,
        "fact_count": 0,
        "review_count": 0,
        "failure_count": 0,
    }
    seeded_connection.execute(
        insert(run_reports).values(
            id="01J00000000000000000000014", crawl_run_id=RUN_ID, **counts
        )
    )

    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(run_reports).values(
                id="01J00000000000000000000015", crawl_run_id=RUN_ID, **counts
            )
        )


def test_confidence_must_be_between_zero_and_one(seeded_connection: Connection) -> None:
    seeded_connection.execute(
        insert(extraction_runs).values(
            id=EXTRACTION_RUN_ID,
            document_version_id=DOCUMENT_VERSION_ID,
            input_fingerprint="c" * 64,
            extractor_name="text_pdf",
            extractor_version="1.0.0",
            method="text",
            status="completed",
        )
    )

    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(extracted_facts).values(
                id=FACT_ID,
                extraction_run_id=EXTRACTION_RUN_ID,
                fact_fingerprint="d" * 64,
                fact_type="horse_name",
                subject_key="race-1-entry-1",
                normalized_value="Ejemplo",
                raw_value="EJEMPLO",
                confidence=1.01,
                requires_review=False,
            )
        )


def test_evidence_page_number_must_be_positive(seeded_connection: Connection) -> None:
    seeded_connection.execute(
        insert(extraction_runs).values(
            id=EXTRACTION_RUN_ID,
            document_version_id=DOCUMENT_VERSION_ID,
            input_fingerprint="c" * 64,
            extractor_name="text_pdf",
            extractor_version="1.0.0",
            method="text",
            status="completed",
        )
    )
    seeded_connection.execute(
        insert(extracted_facts).values(
            id=FACT_ID,
            extraction_run_id=EXTRACTION_RUN_ID,
            fact_fingerprint="d" * 64,
            fact_type="horse_name",
            subject_key="race-1-entry-1",
            normalized_value="Ejemplo",
            raw_value="EJEMPLO",
            confidence=0.5,
            requires_review=True,
        )
    )

    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(fact_evidence).values(
                id="01J00000000000000000000016",
                fact_id=FACT_ID,
                page_number=0,
                snippet="EJEMPLO",
                extraction_method="text",
            )
        )


def test_run_report_counters_cannot_be_negative(seeded_connection: Connection) -> None:
    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(run_reports).values(
                id="01J00000000000000000000017",
                crawl_run_id=RUN_ID,
                status="completed",
                discovered_count=-1,
                downloaded_count=0,
                deduplicated_count=0,
                fact_count=0,
                review_count=0,
                failure_count=0,
            )
        )


def test_master_normalized_name_is_unique(seeded_connection: Connection) -> None:
    values = {
        "canonical_name": "J H SUAREZ",
        "normalized_name": "j h suarez",
        "confirmation_status": "confirmed",
        "created_at": OBSERVED_AT,
    }
    seeded_connection.execute(
        insert(jockeys).values(id="01J00000000000000000000020", **values)
    )

    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(jockeys).values(id="01J00000000000000000000021", **values)
        )


def test_master_confirmation_status_is_checked(seeded_connection: Connection) -> None:
    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(horses).values(
                id="01J00000000000000000000022",
                canonical_name="RUIDOSO",
                normalized_name="ruidoso",
                confirmation_status="guessed",
                created_at=OBSERVED_AT,
            )
        )


def test_race_identity_and_entry_mandil_are_unique(seeded_connection: Connection) -> None:
    entity_values = {
        "confirmation_status": "confirmed",
        "created_at": OBSERVED_AT,
    }
    seeded_connection.execute(
        insert(horses).values(
            id="01J00000000000000000000023",
            canonical_name="WAYTT",
            normalized_name="waytt",
            **entity_values,
        )
    )
    seeded_connection.execute(
        insert(jockeys).values(
            id="01J00000000000000000000024",
            canonical_name="J H SUAREZ",
            normalized_name="j h suarez",
            **entity_values,
        )
    )
    seeded_connection.execute(
        insert(trainers).values(
            id="01J00000000000000000000025",
            canonical_name="R MELGAREJO",
            normalized_name="r melgarejo",
            **entity_values,
        )
    )
    seeded_connection.execute(
        insert(studs).values(
            id="01J00000000000000000000026",
            canonical_name="S.B.P.",
            normalized_name="s b p",
            **entity_values,
        )
    )
    race_values = {
        "source_document_version_id": DOCUMENT_VERSION_ID,
        "meeting_code": "202647",
        "race_number": 1,
        "scheduled_date": OBSERVED_AT.date(),
        "distance_meters": 1000,
        "surface": "arena",
        "confirmation_status": "confirmed",
        "created_at": OBSERVED_AT,
    }
    seeded_connection.execute(
        insert(races).values(id="01J00000000000000000000027", **race_values)
    )
    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(races).values(id="01J00000000000000000000028", **race_values)
        )

    seeded_connection.execute(
        insert(extraction_runs).values(
            id=EXTRACTION_RUN_ID,
            document_version_id=DOCUMENT_VERSION_ID,
            input_fingerprint="e" * 64,
            extractor_name="pdfplumber-hipico-text",
            extractor_version="3",
            method="text",
            status="completed",
        )
    )
    for fact_id, fingerprint in (
        ("01J00000000000000000000029", "f" * 64),
        ("01J00000000000000000000030", "1" * 64),
    ):
        seeded_connection.execute(
            insert(extracted_facts).values(
                id=fact_id,
                extraction_run_id=EXTRACTION_RUN_ID,
                fact_fingerprint=fingerprint,
                fact_type="race_entry",
                subject_key=fact_id,
                normalized_value="{}",
                raw_value="row",
                confidence=0.95,
                requires_review=False,
            )
        )
    entry_values = {
        "race_id": "01J00000000000000000000027",
        "horse_id": "01J00000000000000000000023",
        "jockey_id": "01J00000000000000000000024",
        "trainer_id": "01J00000000000000000000025",
        "stud_id": "01J00000000000000000000026",
        "mandil": 1,
        "weight": 56,
        "created_at": OBSERVED_AT,
    }
    seeded_connection.execute(
        insert(race_entries).values(
            id="01J00000000000000000000031",
            source_fact_id="01J00000000000000000000029",
            **entry_values,
        )
    )
    with pytest.raises(IntegrityError):
        seeded_connection.execute(
            insert(race_entries).values(
                id="01J00000000000000000000032",
                source_fact_id="01J00000000000000000000030",
                **entry_values,
            )
        )


@pytest.mark.parametrize(
    "invalid_values",
    [
        {"finishing_position": 0},
        {"distance_meters": 0},
        {"elapsed_time_seconds": Decimal("0")},
        {"surface": "barro"},
        {"track_condition": ""},
        {"race_number": 0},
    ],
)
def test_historical_result_constraints_reject_invalid_values(
    migrated_engine: Engine, invalid_values: dict[str, object]
) -> None:
    horse_id = "01J00000000000000000000501"
    batch_id = "01J00000000000000000000502"
    with migrated_engine.begin() as connection:
        connection.execute(
            insert(horses).values(
                id=horse_id,
                canonical_name="WAYTT",
                normalized_name="waytt",
                confirmation_status="confirmed",
                created_at=OBSERVED_AT,
            )
        )
        connection.execute(
            insert(history_import_batches).values(
                id=batch_id,
                file_sha256="c" * 64,
                source_filename="history.csv",
                file_format="csv",
                row_count=1,
                imported_at=OBSERVED_AT,
            )
        )
    values: dict[str, object] = {
        "id": "01J00000000000000000000503",
        "import_batch_id": batch_id,
        "horse_id": horse_id,
        "race_date": date(2026, 10, 24),
        "finishing_position": 1,
        "distance_meters": 1000,
        "elapsed_time_seconds": Decimal("58.940"),
        "surface": "arena",
        "track_condition": "seca",
        "meeting_code": "202643",
        "race_number": 3,
        "row_fingerprint": "d" * 64,
        "created_at": OBSERVED_AT,
    }
    values.update(invalid_values)

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(insert(horse_race_results).values(**values))
