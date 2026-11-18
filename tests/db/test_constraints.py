from collections.abc import Iterator
from datetime import UTC, datetime

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
    processing_tasks,
    run_reports,
    source_registry,
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
