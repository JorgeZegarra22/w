"""SQLAlchemy Core schema for the approved Entregable 1 data model."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _ulid(name: str, *, primary_key: bool = False) -> Column[str]:
    return Column(name, String(26), primary_key=primary_key, nullable=False)


def _sha256(name: str, *, primary_key: bool = False) -> Column[str]:
    return Column(name, String(64), primary_key=primary_key, nullable=False)


source_registry = Table(
    "source_registry",
    metadata,
    _ulid("id", primary_key=True),
    Column("code", String(100), nullable=False),
    Column("name", String(255), nullable=False),
    Column("base_url", String(2048), nullable=False),
    Column("rate_limit_ms", Integer, nullable=False),
    Column("enabled", Boolean, nullable=False),
    UniqueConstraint("code", name="uq_source_registry_code"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("rate_limit_ms >= 0", name="rate_limit_nonnegative"),
)

source_policy_snapshots = Table(
    "source_policy_snapshots",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_id",
        String(26),
        ForeignKey("source_registry.id", name="fk_policy_snapshot_source"),
        nullable=False,
    ),
    _sha256("robots_sha256"),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("crawl_allowed", Boolean, nullable=False),
    Column("policy_status", String(50), nullable=False),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(robots_sha256) = 64", name="robots_sha256_length"),
    CheckConstraint(
        "policy_status IN ('allowed', 'denied', 'unavailable', 'error')",
        name="policy_status_values",
    ),
)

source_checkpoints = Table(
    "source_checkpoints",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_id",
        String(26),
        ForeignKey("source_registry.id", name="fk_checkpoint_source"),
        nullable=False,
    ),
    Column("checkpoint_key", String(255), nullable=False),
    Column("checkpoint_value", Text, nullable=False),
    Column("last_success_at", DateTime(timezone=True)),
    UniqueConstraint(
        "source_id", "checkpoint_key", name="uq_source_checkpoints_source_key"
    ),
    CheckConstraint("length(id) = 26", name="id_length"),
)

crawl_runs = Table(
    "crawl_runs",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_id",
        String(26),
        ForeignKey("source_registry.id", name="fk_crawl_run_source"),
        nullable=False,
    ),
    Column("correlation_id", String(255), nullable=False),
    Column("status", String(50), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    UniqueConstraint("correlation_id", name="uq_crawl_runs_correlation_id"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint(
        "status IN ('running', 'completed', 'completed_with_reviews', "
        "'partial_failure', 'deferred', 'failed')",
        name="status_values",
    ),
)
Index("ix_crawl_runs_source_id_started_at", crawl_runs.c.source_id, crawl_runs.c.started_at)

fetch_attempts = Table(
    "fetch_attempts",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "crawl_run_id",
        String(26),
        ForeignKey("crawl_runs.id", name="fk_fetch_attempt_crawl_run"),
        nullable=False,
    ),
    Column("url", Text, nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("response_status", Integer),
    Column("outcome", String(50), nullable=False),
    Column("error_code", String(100)),
    UniqueConstraint(
        "crawl_run_id", "url", "attempt_no", name="uq_fetch_attempts_run_url_attempt"
    ),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("attempt_no > 0", name="attempt_positive"),
    CheckConstraint(
        "response_status IS NULL OR (response_status >= 100 AND response_status <= 599)",
        name="response_status_range",
    ),
    CheckConstraint(
        "outcome IN ('success', 'not_modified', 'retryable_error', 'permanent_error')",
        name="outcome_values",
    ),
)

blob_objects = Table(
    "blob_objects",
    metadata,
    _sha256("sha256", primary_key=True),
    Column("byte_size", BigInteger, nullable=False),
    Column("media_type", String(255), nullable=False),
    Column("storage_key", Text, nullable=False),
    Column("first_stored_at", DateTime(timezone=True), nullable=False),
    Column("retained_locally", Boolean, nullable=False),
    CheckConstraint("length(sha256) = 64", name="sha256_length"),
    CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
)

http_cache_entries = Table(
    "http_cache_entries",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_id",
        String(26),
        ForeignKey("source_registry.id", name="fk_http_cache_source"),
        nullable=False,
    ),
    Column(
        "body_blob_sha256",
        String(64),
        ForeignKey("blob_objects.sha256", name="fk_http_cache_blob"),
        nullable=False,
    ),
    _sha256("request_fingerprint"),
    Column("canonical_url", Text, nullable=False),
    Column("etag", String(1024)),
    Column("last_modified", String(255)),
    Column("expires_at", DateTime(timezone=True)),
    UniqueConstraint("request_fingerprint", name="uq_http_cache_request_fingerprint"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(body_blob_sha256) = 64", name="body_sha256_length"),
    CheckConstraint("length(request_fingerprint) = 64", name="request_fingerprint_length"),
)

publications = Table(
    "publications",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_id",
        String(26),
        ForeignKey("source_registry.id", name="fk_publication_source"),
        nullable=False,
    ),
    Column("canonical_url", Text, nullable=False),
    Column("publication_type", String(100), nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("source_id", "canonical_url", name="uq_publications_source_url"),
    CheckConstraint("length(id) = 26", name="id_length"),
)
Index("ix_publications_first_seen_at", publications.c.first_seen_at)
Index("ix_publications_last_seen_at", publications.c.last_seen_at)

publication_versions = Table(
    "publication_versions",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "publication_id",
        String(26),
        ForeignKey("publications.id", name="fk_publication_version_publication"),
        nullable=False,
    ),
    Column(
        "crawl_run_id",
        String(26),
        ForeignKey("crawl_runs.id", name="fk_publication_version_crawl_run"),
        nullable=False,
    ),
    _sha256("content_sha256"),
    Column("title", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("detected_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "publication_id", "content_sha256", name="uq_publication_versions_publication_hash"
    ),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(content_sha256) = 64", name="content_sha256_length"),
)

documents = Table(
    "documents",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_id",
        String(26),
        ForeignKey("source_registry.id", name="fk_document_source"),
        nullable=False,
    ),
    Column("canonical_url", Text, nullable=False),
    Column("document_type", String(100), nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("source_id", "canonical_url", name="uq_documents_source_url"),
    CheckConstraint("length(id) = 26", name="id_length"),
)
Index("ix_documents_first_seen_at", documents.c.first_seen_at)
Index("ix_documents_last_seen_at", documents.c.last_seen_at)

publication_document_links = Table(
    "publication_document_links",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "publication_version_id",
        String(26),
        ForeignKey(
            "publication_versions.id", name="fk_publication_document_link_publication_version"
        ),
        nullable=False,
    ),
    Column(
        "document_id",
        String(26),
        ForeignKey("documents.id", name="fk_publication_document_link_document"),
        nullable=False,
    ),
    Column("discovered_url", Text, nullable=False),
    Column("link_context", Text),
    Column("discovery_method", String(50), nullable=False),
    UniqueConstraint(
        "publication_version_id",
        "document_id",
        "discovered_url",
        name="uq_publication_document_links_version_document_url",
    ),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint(
        "discovery_method IN ('html', 'script', 'endpoint', 'rendered')",
        name="discovery_method_values",
    ),
)

document_versions = Table(
    "document_versions",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "document_id",
        String(26),
        ForeignKey("documents.id", name="fk_document_version_document"),
        nullable=False,
    ),
    Column(
        "blob_sha256",
        String(64),
        ForeignKey("blob_objects.sha256", name="fk_document_version_blob"),
        nullable=False,
    ),
    Column(
        "crawl_run_id",
        String(26),
        ForeignKey("crawl_runs.id", name="fk_document_version_crawl_run"),
        nullable=False,
    ),
    Column("original_filename", Text),
    Column("detected_at", DateTime(timezone=True), nullable=False),
    Column("downloaded_at", DateTime(timezone=True)),
    Column("processing_status", String(50), nullable=False),
    UniqueConstraint(
        "document_id", "blob_sha256", name="uq_document_versions_document_blob"
    ),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(blob_sha256) = 64", name="blob_sha256_length"),
    CheckConstraint(
        "processing_status IN ('pending', 'extracting', 'extracted', 'needs_ocr', 'failed')",
        name="processing_status_values",
    ),
)
Index("ix_document_versions_processing_status", document_versions.c.processing_status)

extraction_runs = Table(
    "extraction_runs",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "document_version_id",
        String(26),
        ForeignKey("document_versions.id", name="fk_extraction_run_document_version"),
        nullable=False,
    ),
    _sha256("input_fingerprint"),
    Column("extractor_name", String(255), nullable=False),
    Column("extractor_version", String(100), nullable=False),
    Column("method", String(50), nullable=False),
    Column("status", String(50), nullable=False),
    UniqueConstraint("input_fingerprint", name="uq_extraction_runs_input_fingerprint"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(input_fingerprint) = 64", name="input_fingerprint_length"),
    CheckConstraint("method IN ('text', 'ocr')", name="method_values"),
    CheckConstraint(
        "status IN ('running', 'completed', 'needs_ocr', 'failed')", name="status_values"
    ),
)

extracted_facts = Table(
    "extracted_facts",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "extraction_run_id",
        String(26),
        ForeignKey("extraction_runs.id", name="fk_extracted_fact_extraction_run"),
        nullable=False,
    ),
    _sha256("fact_fingerprint"),
    Column("fact_type", String(100), nullable=False),
    Column("subject_key", String(255), nullable=False),
    Column("normalized_value", Text, nullable=False),
    Column("raw_value", Text, nullable=False),
    Column("confidence", Numeric(5, 4), nullable=False),
    Column("requires_review", Boolean, nullable=False),
    UniqueConstraint("fact_fingerprint", name="uq_extracted_facts_fact_fingerprint"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(fact_fingerprint) = 64", name="fact_fingerprint_length"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
)

fact_evidence = Table(
    "fact_evidence",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "fact_id",
        String(26),
        ForeignKey("extracted_facts.id", name="fk_fact_evidence_fact"),
        nullable=False,
    ),
    Column("page_number", Integer, nullable=False),
    Column("bbox_x0", Numeric(12, 4)),
    Column("bbox_y0", Numeric(12, 4)),
    Column("bbox_x1", Numeric(12, 4)),
    Column("bbox_y1", Numeric(12, 4)),
    Column("snippet", Text, nullable=False),
    Column("extraction_method", String(50), nullable=False),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("page_number > 0", name="page_number_positive"),
    CheckConstraint("length(snippet) <= 500", name="snippet_length"),
    CheckConstraint("extraction_method IN ('text', 'ocr')", name="method_values"),
    CheckConstraint(
        "(bbox_x0 IS NULL AND bbox_y0 IS NULL AND bbox_x1 IS NULL AND bbox_y1 IS NULL) "
        "OR (bbox_x0 IS NOT NULL AND bbox_y0 IS NOT NULL AND bbox_x1 IS NOT NULL "
        "AND bbox_y1 IS NOT NULL AND bbox_x1 >= bbox_x0 AND bbox_y1 >= bbox_y0)",
        name="bbox_complete_and_ordered",
    ),
)

review_items = Table(
    "review_items",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "fact_id",
        String(26),
        ForeignKey("extracted_facts.id", name="fk_review_item_fact"),
        nullable=False,
    ),
    Column("status", String(50), nullable=False),
    Column("reason_code", String(100), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    UniqueConstraint("fact_id", name="uq_review_items_fact_id"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint(
        "status IN ('pending', 'accepted', 'corrected', 'rejected')", name="status_values"
    ),
)
Index("ix_review_items_status_created_at", review_items.c.status, review_items.c.created_at)

review_decisions = Table(
    "review_decisions",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "review_item_id",
        String(26),
        ForeignKey("review_items.id", name="fk_review_decision_review_item"),
        nullable=False,
    ),
    Column("decision", String(50), nullable=False),
    Column("reviewer", String(255), nullable=False),
    Column("note", Text),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint(
        "decision IN ('accepted', 'corrected', 'rejected')", name="decision_values"
    ),
)

processing_tasks = Table(
    "processing_tasks",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "crawl_run_id",
        String(26),
        ForeignKey("crawl_runs.id", name="fk_processing_task_crawl_run"),
        nullable=False,
    ),
    Column(
        "document_version_id",
        String(26),
        ForeignKey("document_versions.id", name="fk_processing_task_document_version"),
        nullable=False,
    ),
    _sha256("idempotency_key"),
    Column("task_type", String(100), nullable=False),
    Column("status", String(50), nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("available_at", DateTime(timezone=True)),
    Column("last_error_code", String(100)),
    UniqueConstraint("idempotency_key", name="uq_processing_tasks_idempotency_key"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(idempotency_key) = 64", name="idempotency_key_length"),
    CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
    CheckConstraint(
        "status IN ('pending', 'running', 'deferred', 'completed', 'failed')",
        name="status_values",
    ),
)
Index(
    "ix_processing_tasks_status_available_at",
    processing_tasks.c.status,
    processing_tasks.c.available_at,
)

run_reports = Table(
    "run_reports",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "crawl_run_id",
        String(26),
        ForeignKey("crawl_runs.id", name="fk_run_report_crawl_run"),
        nullable=False,
    ),
    Column("status", String(50), nullable=False),
    Column("discovered_count", Integer, nullable=False),
    Column("downloaded_count", Integer, nullable=False),
    Column("deduplicated_count", Integer, nullable=False),
    Column("fact_count", Integer, nullable=False),
    Column("review_count", Integer, nullable=False),
    Column("failure_count", Integer, nullable=False),
    UniqueConstraint("crawl_run_id", name="uq_run_reports_crawl_run_id"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint(
        "status IN ('completed', 'completed_with_reviews', 'partial_failure', "
        "'deferred', 'failed')",
        name="status_values",
    ),
    CheckConstraint(
        "discovered_count >= 0 AND downloaded_count >= 0 AND deduplicated_count >= 0 "
        "AND fact_count >= 0 AND review_count >= 0 AND failure_count >= 0",
        name="counts_nonnegative",
    ),
)

run_metrics = Table(
    "run_metrics",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "run_report_id",
        String(26),
        ForeignKey("run_reports.id", name="fk_run_metric_run_report"),
        nullable=False,
    ),
    Column("metric_name", String(255), nullable=False),
    Column("metric_value", Integer, nullable=False),
    UniqueConstraint("run_report_id", "metric_name", name="uq_run_metrics_report_name"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("metric_value >= 0", name="metric_value_nonnegative"),
)


def _master_entity_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        _ulid("id", primary_key=True),
        Column("canonical_name", String(255), nullable=False),
        Column("normalized_name", String(255), nullable=False),
        Column("confirmation_status", String(20), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("normalized_name", name=f"uq_{name}_normalized_name"),
        CheckConstraint("length(id) = 26", name="id_length"),
        CheckConstraint("length(trim(canonical_name)) > 0", name="canonical_name_nonempty"),
        CheckConstraint("length(trim(normalized_name)) > 0", name="normalized_name_nonempty"),
        CheckConstraint(
            "confirmation_status IN ('confirmed', 'unconfirmed')",
            name="confirmation_status_values",
        ),
    )


horses = _master_entity_table("horses")
jockeys = _master_entity_table("jockeys")
trainers = _master_entity_table("trainers")
studs = _master_entity_table("studs")

races = Table(
    "races",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_document_version_id",
        String(26),
        ForeignKey("document_versions.id", name="fk_race_document_version"),
        nullable=False,
    ),
    Column("meeting_code", String(20), nullable=False),
    Column("race_number", Integer, nullable=False),
    Column("scheduled_date", Date, nullable=False),
    Column("distance_meters", Integer, nullable=False),
    Column("surface", String(30), nullable=False),
    Column("confirmation_status", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("meeting_code", "race_number", name="uq_races_meeting_race"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("race_number > 0", name="race_number_positive"),
    CheckConstraint("distance_meters > 0", name="distance_positive"),
    CheckConstraint("surface IN ('arena', 'cesped')", name="surface_values"),
    CheckConstraint(
        "confirmation_status IN ('confirmed', 'unconfirmed')",
        name="confirmation_status_values",
    ),
)

race_entries = Table(
    "race_entries",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "race_id",
        String(26),
        ForeignKey("races.id", name="fk_race_entry_race"),
        nullable=False,
    ),
    Column(
        "horse_id",
        String(26),
        ForeignKey("horses.id", name="fk_race_entry_horse"),
        nullable=False,
    ),
    Column(
        "jockey_id",
        String(26),
        ForeignKey("jockeys.id", name="fk_race_entry_jockey"),
        nullable=False,
    ),
    Column(
        "trainer_id",
        String(26),
        ForeignKey("trainers.id", name="fk_race_entry_trainer"),
        nullable=False,
    ),
    Column(
        "stud_id",
        String(26),
        ForeignKey("studs.id", name="fk_race_entry_stud"),
        nullable=False,
    ),
    Column(
        "source_fact_id",
        String(26),
        ForeignKey("extracted_facts.id", name="fk_race_entry_source_fact"),
        nullable=False,
    ),
    Column("mandil", Integer, nullable=False),
    Column("weight", Numeric(5, 2), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("source_fact_id", name="uq_race_entries_source_fact"),
    UniqueConstraint("race_id", "mandil", name="uq_race_entries_race_mandil"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("mandil > 0", name="mandil_positive"),
    CheckConstraint("weight > 0", name="weight_positive"),
)

history_import_batches = Table(
    "history_import_batches",
    metadata,
    _ulid("id", primary_key=True),
    _sha256("file_sha256"),
    Column("source_filename", Text, nullable=False),
    Column("file_format", String(20), nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("imported_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("file_sha256", name="uq_history_import_batches_file_sha256"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("length(file_sha256) = 64", name="file_sha256_length"),
    CheckConstraint("file_sha256 = lower(file_sha256)", name="file_sha256_lowercase"),
    CheckConstraint("file_format = 'csv'", name="file_format_csv"),
    CheckConstraint("row_count > 0", name="row_count_positive"),
)

horse_race_results = Table(
    "horse_race_results",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "import_batch_id",
        String(26),
        ForeignKey("history_import_batches.id", name="fk_horse_result_import_batch"),
        nullable=False,
    ),
    Column(
        "horse_id",
        String(26),
        ForeignKey("horses.id", name="fk_horse_result_horse"),
        nullable=False,
    ),
    Column("race_date", Date, nullable=False),
    Column("finishing_position", Integer, nullable=False),
    Column("distance_meters", Integer, nullable=False),
    Column("elapsed_time_seconds", Numeric(9, 3), nullable=False),
    Column("surface", String(20), nullable=False),
    Column("track_condition", String(50), nullable=False),
    Column("meeting_code", String(20)),
    Column("race_number", Integer),
    _sha256("row_fingerprint"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("row_fingerprint", name="uq_horse_race_results_row_fingerprint"),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("finishing_position > 0", name="position_positive"),
    CheckConstraint("distance_meters > 0", name="distance_positive"),
    CheckConstraint("elapsed_time_seconds > 0", name="elapsed_time_positive"),
    CheckConstraint("surface IN ('arena', 'cesped')", name="surface_values"),
    CheckConstraint(
        "length(trim(track_condition)) > 0", name="track_condition_nonempty"
    ),
    CheckConstraint("race_number IS NULL OR race_number > 0", name="race_number_positive"),
    CheckConstraint("length(row_fingerprint) = 64", name="row_fingerprint_length"),
    CheckConstraint(
        "row_fingerprint = lower(row_fingerprint)", name="row_fingerprint_lowercase"
    ),
)
Index(
    "ix_horse_results_horse_date",
    horse_race_results.c.horse_id,
    horse_race_results.c.race_date,
)
Index(
    "ix_horse_results_horse_distance_date",
    horse_race_results.c.horse_id,
    horse_race_results.c.distance_meters,
    horse_race_results.c.race_date,
)
Index(
    "ix_horse_results_horse_surface_date",
    horse_race_results.c.horse_id,
    horse_race_results.c.surface,
    horse_race_results.c.race_date,
)

journalist_picks = Table(
    "journalist_picks",
    metadata,
    _ulid("id", primary_key=True),
    Column(
        "source_document_version_id",
        String(26),
        ForeignKey("document_versions.id", name="fk_journalist_pick_document_version"),
        nullable=False,
    ),
    Column(
        "source_fact_id",
        String(26),
        ForeignKey("extracted_facts.id", name="fk_journalist_pick_source_fact"),
        nullable=False,
    ),
    Column("meeting_code", String(20), nullable=False),
    Column("race_number", Integer, nullable=False),
    Column("selection_rank", Integer, nullable=False),
    Column("mandil", Integer),
    Column("horse_name_raw", String(255), nullable=False),
    Column("journalist_name", String(255), nullable=False),
    Column("confidence", Numeric(5, 4), nullable=False),
    Column("requires_review", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("source_fact_id", name="uq_journalist_picks_source_fact"),
    UniqueConstraint(
        "source_document_version_id",
        "meeting_code",
        "race_number",
        "selection_rank",
        name="uq_journalist_picks_document_race_rank",
    ),
    CheckConstraint("length(id) = 26", name="id_length"),
    CheckConstraint("race_number > 0", name="race_number_positive"),
    CheckConstraint("selection_rank > 0", name="selection_rank_positive"),
    CheckConstraint("mandil IS NULL OR mandil > 0", name="mandil_positive"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
)
Index(
    "ix_journalist_picks_meeting_race",
    journalist_picks.c.meeting_code,
    journalist_picks.c.race_number,
)

horse_stats_snapshots = Table(
    "horse_stats_snapshots",
    metadata,
    _ulid("id", primary_key=True),
    Column("race_entry_id", String(26), ForeignKey("race_entries.id"), nullable=False),
    Column("source_url", Text, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    _sha256("content_hash"),
    Column("profile", JSON(none_as_null=True), nullable=False),
    UniqueConstraint("race_entry_id", "content_hash", name="uq_horse_snapshot_entry_hash"),
    CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
)
Index(
    "ix_horse_stats_snapshots_entry_fetched",
    horse_stats_snapshots.c.race_entry_id,
    horse_stats_snapshots.c.fetched_at,
)
