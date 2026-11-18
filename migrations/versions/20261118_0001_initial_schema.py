"""Create the Entregable 1 persistence schema.

Revision ID: 20261118_0001
Revises: None
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ulid(name: str, *, primary_key: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.String(26), primary_key=primary_key, nullable=False)


def _sha256(name: str, *, primary_key: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.String(64), primary_key=primary_key, nullable=False)


def upgrade() -> None:
    op.create_table(
        "source_registry",
        _ulid("id", primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("rate_limit_ms", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code", name="uq_source_registry_code"),
        sa.CheckConstraint("length(id) = 26", name="ck_source_registry_id_length"),
        sa.CheckConstraint(
            "rate_limit_ms >= 0", name="ck_source_registry_rate_limit_nonnegative"
        ),
    )
    op.create_table(
        "blob_objects",
        _sha256("sha256", primary_key=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("first_stored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retained_locally", sa.Boolean(), nullable=False),
        sa.CheckConstraint("length(sha256) = 64", name="ck_blob_objects_sha256_length"),
        sa.CheckConstraint(
            "byte_size >= 0", name="ck_blob_objects_byte_size_nonnegative"
        ),
    )
    op.create_table(
        "source_policy_snapshots",
        _ulid("id", primary_key=True),
        sa.Column("source_id", sa.String(26), nullable=False),
        _sha256("robots_sha256"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("crawl_allowed", sa.Boolean(), nullable=False),
        sa.Column("policy_status", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], name="fk_policy_snapshot_source"
        ),
        sa.CheckConstraint(
            "length(id) = 26", name="ck_source_policy_snapshots_id_length"
        ),
        sa.CheckConstraint(
            "length(robots_sha256) = 64",
            name="ck_source_policy_snapshots_robots_sha256_length",
        ),
        sa.CheckConstraint(
            "policy_status IN ('allowed', 'denied', 'unavailable', 'error')",
            name="ck_source_policy_snapshots_policy_status_values",
        ),
    )
    op.create_table(
        "source_checkpoints",
        _ulid("id", primary_key=True),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("checkpoint_key", sa.String(255), nullable=False),
        sa.Column("checkpoint_value", sa.Text(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], name="fk_checkpoint_source"
        ),
        sa.UniqueConstraint(
            "source_id", "checkpoint_key", name="uq_source_checkpoints_source_key"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_source_checkpoints_id_length"),
    )
    op.create_table(
        "crawl_runs",
        _ulid("id", primary_key=True),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("correlation_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], name="fk_crawl_run_source"
        ),
        sa.UniqueConstraint("correlation_id", name="uq_crawl_runs_correlation_id"),
        sa.CheckConstraint("length(id) = 26", name="ck_crawl_runs_id_length"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'completed_with_reviews', "
            "'partial_failure', 'deferred', 'failed')",
            name="ck_crawl_runs_status_values",
        ),
    )
    op.create_index(
        "ix_crawl_runs_source_id_started_at", "crawl_runs", ["source_id", "started_at"]
    )
    op.create_table(
        "fetch_attempts",
        _ulid("id", primary_key=True),
        sa.Column("crawl_run_id", sa.String(26), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.ForeignKeyConstraint(
            ["crawl_run_id"], ["crawl_runs.id"], name="fk_fetch_attempt_crawl_run"
        ),
        sa.UniqueConstraint(
            "crawl_run_id", "url", "attempt_no", name="uq_fetch_attempts_run_url_attempt"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_fetch_attempts_id_length"),
        sa.CheckConstraint("attempt_no > 0", name="ck_fetch_attempts_attempt_positive"),
        sa.CheckConstraint(
            "response_status IS NULL OR (response_status >= 100 AND response_status <= 599)",
            name="ck_fetch_attempts_response_status_range",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'not_modified', 'retryable_error', 'permanent_error')",
            name="ck_fetch_attempts_outcome_values",
        ),
    )
    op.create_table(
        "http_cache_entries",
        _ulid("id", primary_key=True),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("body_blob_sha256", sa.String(64), nullable=False),
        _sha256("request_fingerprint"),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("etag", sa.String(1024)),
        sa.Column("last_modified", sa.String(255)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], name="fk_http_cache_source"
        ),
        sa.ForeignKeyConstraint(
            ["body_blob_sha256"], ["blob_objects.sha256"], name="fk_http_cache_blob"
        ),
        sa.UniqueConstraint(
            "request_fingerprint", name="uq_http_cache_request_fingerprint"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_http_cache_entries_id_length"),
        sa.CheckConstraint(
            "length(body_blob_sha256) = 64",
            name="ck_http_cache_entries_body_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_http_cache_entries_request_fingerprint_length",
        ),
    )
    op.create_table(
        "publications",
        _ulid("id", primary_key=True),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("publication_type", sa.String(100), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], name="fk_publication_source"
        ),
        sa.UniqueConstraint("source_id", "canonical_url", name="uq_publications_source_url"),
        sa.CheckConstraint("length(id) = 26", name="ck_publications_id_length"),
    )
    op.create_index("ix_publications_first_seen_at", "publications", ["first_seen_at"])
    op.create_index("ix_publications_last_seen_at", "publications", ["last_seen_at"])
    op.create_table(
        "publication_versions",
        _ulid("id", primary_key=True),
        sa.Column("publication_id", sa.String(26), nullable=False),
        sa.Column("crawl_run_id", sa.String(26), nullable=False),
        _sha256("content_sha256"),
        sa.Column("title", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            name="fk_publication_version_publication",
        ),
        sa.ForeignKeyConstraint(
            ["crawl_run_id"], ["crawl_runs.id"], name="fk_publication_version_crawl_run"
        ),
        sa.UniqueConstraint(
            "publication_id",
            "content_sha256",
            name="uq_publication_versions_publication_hash",
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_publication_versions_id_length"),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_publication_versions_content_sha256_length",
        ),
    )
    op.create_table(
        "documents",
        _ulid("id", primary_key=True),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source_registry.id"], name="fk_document_source"
        ),
        sa.UniqueConstraint("source_id", "canonical_url", name="uq_documents_source_url"),
        sa.CheckConstraint("length(id) = 26", name="ck_documents_id_length"),
    )
    op.create_index("ix_documents_first_seen_at", "documents", ["first_seen_at"])
    op.create_index("ix_documents_last_seen_at", "documents", ["last_seen_at"])
    op.create_table(
        "publication_document_links",
        _ulid("id", primary_key=True),
        sa.Column("publication_version_id", sa.String(26), nullable=False),
        sa.Column("document_id", sa.String(26), nullable=False),
        sa.Column("discovered_url", sa.Text(), nullable=False),
        sa.Column("link_context", sa.Text()),
        sa.Column("discovery_method", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(
            ["publication_version_id"],
            ["publication_versions.id"],
            name="fk_publication_document_link_publication_version",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_publication_document_link_document"
        ),
        sa.UniqueConstraint(
            "publication_version_id",
            "document_id",
            "discovered_url",
            name="uq_publication_document_links_version_document_url",
        ),
        sa.CheckConstraint(
            "length(id) = 26", name="ck_publication_document_links_id_length"
        ),
        sa.CheckConstraint(
            "discovery_method IN ('html', 'script', 'endpoint', 'rendered')",
            name="ck_publication_document_links_discovery_method_values",
        ),
    )
    op.create_table(
        "document_versions",
        _ulid("id", primary_key=True),
        sa.Column("document_id", sa.String(26), nullable=False),
        sa.Column("blob_sha256", sa.String(64), nullable=False),
        sa.Column("crawl_run_id", sa.String(26), nullable=False),
        sa.Column("original_filename", sa.Text()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True)),
        sa.Column("processing_status", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_document_version_document"
        ),
        sa.ForeignKeyConstraint(
            ["blob_sha256"], ["blob_objects.sha256"], name="fk_document_version_blob"
        ),
        sa.ForeignKeyConstraint(
            ["crawl_run_id"], ["crawl_runs.id"], name="fk_document_version_crawl_run"
        ),
        sa.UniqueConstraint(
            "document_id", "blob_sha256", name="uq_document_versions_document_blob"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_document_versions_id_length"),
        sa.CheckConstraint(
            "length(blob_sha256) = 64", name="ck_document_versions_blob_sha256_length"
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'extracting', 'extracted', 'needs_ocr', 'failed')",
            name="ck_document_versions_processing_status_values",
        ),
    )
    op.create_index(
        "ix_document_versions_processing_status", "document_versions", ["processing_status"]
    )
    op.create_table(
        "extraction_runs",
        _ulid("id", primary_key=True),
        sa.Column("document_version_id", sa.String(26), nullable=False),
        _sha256("input_fingerprint"),
        sa.Column("extractor_name", sa.String(255), nullable=False),
        sa.Column("extractor_version", sa.String(100), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_extraction_run_document_version",
        ),
        sa.UniqueConstraint(
            "input_fingerprint", name="uq_extraction_runs_input_fingerprint"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_extraction_runs_id_length"),
        sa.CheckConstraint(
            "length(input_fingerprint) = 64",
            name="ck_extraction_runs_input_fingerprint_length",
        ),
        sa.CheckConstraint(
            "method IN ('text', 'ocr')", name="ck_extraction_runs_method_values"
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'needs_ocr', 'failed')",
            name="ck_extraction_runs_status_values",
        ),
    )
    op.create_table(
        "extracted_facts",
        _ulid("id", primary_key=True),
        sa.Column("extraction_run_id", sa.String(26), nullable=False),
        _sha256("fact_fingerprint"),
        sa.Column("fact_type", sa.String(100), nullable=False),
        sa.Column("subject_key", sa.String(255), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"], ["extraction_runs.id"], name="fk_extracted_fact_extraction_run"
        ),
        sa.UniqueConstraint(
            "fact_fingerprint", name="uq_extracted_facts_fact_fingerprint"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_extracted_facts_id_length"),
        sa.CheckConstraint(
            "length(fact_fingerprint) = 64",
            name="ck_extracted_facts_fact_fingerprint_length",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_extracted_facts_confidence_range",
        ),
    )
    op.create_table(
        "fact_evidence",
        _ulid("id", primary_key=True),
        sa.Column("fact_id", sa.String(26), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("bbox_x0", sa.Numeric(12, 4)),
        sa.Column("bbox_y0", sa.Numeric(12, 4)),
        sa.Column("bbox_x1", sa.Numeric(12, 4)),
        sa.Column("bbox_y1", sa.Numeric(12, 4)),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(
            ["fact_id"], ["extracted_facts.id"], name="fk_fact_evidence_fact"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_fact_evidence_id_length"),
        sa.CheckConstraint(
            "page_number > 0", name="ck_fact_evidence_page_number_positive"
        ),
        sa.CheckConstraint("length(snippet) <= 500", name="ck_fact_evidence_snippet_length"),
        sa.CheckConstraint(
            "extraction_method IN ('text', 'ocr')", name="ck_fact_evidence_method_values"
        ),
        sa.CheckConstraint(
            "(bbox_x0 IS NULL AND bbox_y0 IS NULL AND bbox_x1 IS NULL AND bbox_y1 IS NULL) "
            "OR (bbox_x0 IS NOT NULL AND bbox_y0 IS NOT NULL AND bbox_x1 IS NOT NULL "
            "AND bbox_y1 IS NOT NULL AND bbox_x1 >= bbox_x0 AND bbox_y1 >= bbox_y0)",
            name="ck_fact_evidence_bbox_complete_and_ordered",
        ),
    )
    op.create_table(
        "review_items",
        _ulid("id", primary_key=True),
        sa.Column("fact_id", sa.String(26), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["fact_id"], ["extracted_facts.id"], name="fk_review_item_fact"
        ),
        sa.UniqueConstraint("fact_id", name="uq_review_items_fact_id"),
        sa.CheckConstraint("length(id) = 26", name="ck_review_items_id_length"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected', 'rejected')",
            name="ck_review_items_status_values",
        ),
    )
    op.create_index(
        "ix_review_items_status_created_at", "review_items", ["status", "created_at"]
    )
    op.create_table(
        "review_decisions",
        _ulid("id", primary_key=True),
        sa.Column("review_item_id", sa.String(26), nullable=False),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("reviewer", sa.String(255), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_item_id"], ["review_items.id"], name="fk_review_decision_review_item"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_review_decisions_id_length"),
        sa.CheckConstraint(
            "decision IN ('accepted', 'corrected', 'rejected')",
            name="ck_review_decisions_decision_values",
        ),
    )
    op.create_table(
        "processing_tasks",
        _ulid("id", primary_key=True),
        sa.Column("crawl_run_id", sa.String(26), nullable=False),
        sa.Column("document_version_id", sa.String(26), nullable=False),
        _sha256("idempotency_key"),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(100)),
        sa.ForeignKeyConstraint(
            ["crawl_run_id"], ["crawl_runs.id"], name="fk_processing_task_crawl_run"
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_processing_task_document_version",
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_processing_tasks_idempotency_key"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_processing_tasks_id_length"),
        sa.CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_processing_tasks_idempotency_key_length",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_processing_tasks_attempt_count_nonnegative"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'deferred', 'completed', 'failed')",
            name="ck_processing_tasks_status_values",
        ),
    )
    op.create_index(
        "ix_processing_tasks_status_available_at",
        "processing_tasks",
        ["status", "available_at"],
    )
    op.create_table(
        "run_reports",
        _ulid("id", primary_key=True),
        sa.Column("crawl_run_id", sa.String(26), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("downloaded_count", sa.Integer(), nullable=False),
        sa.Column("deduplicated_count", sa.Integer(), nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["crawl_run_id"], ["crawl_runs.id"], name="fk_run_report_crawl_run"
        ),
        sa.UniqueConstraint("crawl_run_id", name="uq_run_reports_crawl_run_id"),
        sa.CheckConstraint("length(id) = 26", name="ck_run_reports_id_length"),
        sa.CheckConstraint(
            "status IN ('completed', 'completed_with_reviews', 'partial_failure', "
            "'deferred', 'failed')",
            name="ck_run_reports_status_values",
        ),
        sa.CheckConstraint(
            "discovered_count >= 0 AND downloaded_count >= 0 AND deduplicated_count >= 0 "
            "AND fact_count >= 0 AND review_count >= 0 AND failure_count >= 0",
            name="ck_run_reports_counts_nonnegative",
        ),
    )
    op.create_table(
        "run_metrics",
        _ulid("id", primary_key=True),
        sa.Column("run_report_id", sa.String(26), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("metric_value", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_report_id"], ["run_reports.id"], name="fk_run_metric_run_report"
        ),
        sa.UniqueConstraint(
            "run_report_id", "metric_name", name="uq_run_metrics_report_name"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_run_metrics_id_length"),
        sa.CheckConstraint(
            "metric_value >= 0", name="ck_run_metrics_metric_value_nonnegative"
        ),
    )


def downgrade() -> None:
    op.drop_table("run_metrics")
    op.drop_table("run_reports")
    op.drop_index("ix_processing_tasks_status_available_at", table_name="processing_tasks")
    op.drop_table("processing_tasks")
    op.drop_table("review_decisions")
    op.drop_index("ix_review_items_status_created_at", table_name="review_items")
    op.drop_table("review_items")
    op.drop_table("fact_evidence")
    op.drop_table("extracted_facts")
    op.drop_table("extraction_runs")
    op.drop_index("ix_document_versions_processing_status", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_table("publication_document_links")
    op.drop_index("ix_documents_last_seen_at", table_name="documents")
    op.drop_index("ix_documents_first_seen_at", table_name="documents")
    op.drop_table("documents")
    op.drop_table("publication_versions")
    op.drop_index("ix_publications_last_seen_at", table_name="publications")
    op.drop_index("ix_publications_first_seen_at", table_name="publications")
    op.drop_table("publications")
    op.drop_table("http_cache_entries")
    op.drop_table("fetch_attempts")
    op.drop_index("ix_crawl_runs_source_id_started_at", table_name="crawl_runs")
    op.drop_table("crawl_runs")
    op.drop_table("source_checkpoints")
    op.drop_table("source_policy_snapshots")
    op.drop_table("blob_objects")
    op.drop_table("source_registry")
