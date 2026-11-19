from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from benter_peru.db.schema import metadata

EXPECTED_TABLES = {
    "blob_objects",
    "crawl_runs",
    "document_versions",
    "documents",
    "extracted_facts",
    "extraction_runs",
    "fact_evidence",
    "fetch_attempts",
    "http_cache_entries",
    "history_import_batches",
    "horse_race_results",
    "horse_stats_snapshots",
    "horses",
    "jockeys",
    "journalist_picks",
    "processing_tasks",
    "publication_document_links",
    "publication_versions",
    "publications",
    "race_entries",
    "races",
    "review_decisions",
    "review_items",
    "run_metrics",
    "run_reports",
    "source_checkpoints",
    "source_policy_snapshots",
    "source_registry",
    "studs",
    "trainers",
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    "source_registry": {("code",)},
    "source_checkpoints": {("source_id", "checkpoint_key")},
    "crawl_runs": {("correlation_id",)},
    "fetch_attempts": {("crawl_run_id", "url", "attempt_no")},
    "http_cache_entries": {("request_fingerprint",)},
    "publications": {("source_id", "canonical_url")},
    "publication_versions": {("publication_id", "content_sha256")},
    "documents": {("source_id", "canonical_url")},
    "publication_document_links": {
        ("publication_version_id", "document_id", "discovered_url")
    },
    "document_versions": {("document_id", "blob_sha256")},
    "extraction_runs": {("input_fingerprint",)},
    "extracted_facts": {("fact_fingerprint",)},
    "review_items": {("fact_id",)},
    "processing_tasks": {("idempotency_key",)},
    "run_reports": {("crawl_run_id",)},
    "run_metrics": {("run_report_id", "metric_name")},
    "horses": {("normalized_name",)},
    "history_import_batches": {("file_sha256",)},
    "horse_race_results": {("row_fingerprint",)},
    "horse_stats_snapshots": {("race_entry_id", "content_hash")},
    "jockeys": {("normalized_name",)},
    "trainers": {("normalized_name",)},
    "studs": {("normalized_name",)},
    "races": {("meeting_code", "race_number")},
    "race_entries": {("source_fact_id",), ("race_id", "mandil")},
    "journalist_picks": {
        ("source_fact_id",),
        ("source_document_version_id", "meeting_code", "race_number", "selection_rank"),
    },
}

EXPECTED_INDEXES = {
    "crawl_runs": {"ix_crawl_runs_source_id_started_at"},
    "document_versions": {"ix_document_versions_processing_status"},
    "horse_race_results": {
        "ix_horse_results_horse_date",
        "ix_horse_results_horse_distance_date",
        "ix_horse_results_horse_surface_date",
    },
    "horse_stats_snapshots": {"ix_horse_stats_snapshots_entry_fetched"},
    "documents": {
        "ix_documents_first_seen_at",
        "ix_documents_last_seen_at",
    },
    "processing_tasks": {"ix_processing_tasks_status_available_at"},
    "publications": {
        "ix_publications_first_seen_at",
        "ix_publications_last_seen_at",
    },
    "review_items": {"ix_review_items_status_created_at"},
    "journalist_picks": {"ix_journalist_picks_meeting_race"},
}


def test_initial_migration_creates_exact_approved_table_inventory(
    migrated_engine: Engine,
) -> None:
    inspector = inspect(migrated_engine)

    assert set(inspector.get_table_names()) - {"alembic_version"} == EXPECTED_TABLES
    assert set(metadata.tables) == EXPECTED_TABLES


def test_sqlite_connections_enforce_foreign_keys(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        enabled = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1


def test_migration_creates_all_approved_unique_constraints(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    actual = {
        table_name: {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table_name)
        }
        for table_name in EXPECTED_UNIQUE_CONSTRAINTS
    }

    assert actual == EXPECTED_UNIQUE_CONSTRAINTS


def test_migration_creates_approved_recovery_indexes(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    actual = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in EXPECTED_INDEXES
    }

    assert actual == EXPECTED_INDEXES
