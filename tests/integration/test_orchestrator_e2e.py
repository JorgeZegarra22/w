"""End-to-end orchestration tests using a local HTTP server and real PDF parser."""

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import metadata
from benter_peru.discovery import SourceDefinition
from benter_peru.extraction.models import ExtractionBundle
from benter_peru.extraction.router import ExtractionRouter
from benter_peru.http.client import HttpClientConfig, ResponsibleHttpClient
from benter_peru.orchestrator import RunOrchestrator
from benter_peru.policy import PolicyGate
from benter_peru.storage.local import LocalBlobStore


def _pdf_bytes() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=letter)
    canvas.drawString(72, 720, "Caballo Ganador")
    canvas.save()
    return stream.getvalue()


class LowConfidenceRouter:
    def __init__(self) -> None:
        self.calls = 0
        self._delegate = ExtractionRouter()

    def extract(self, source: BytesIO) -> ExtractionBundle:
        self.calls += 1
        bundle = self._delegate.extract(source)
        evidence = tuple(
            replace(item, confidence=0.5, requires_review=True)
            for item in bundle.evidence
        )
        return replace(bundle, evidence=evidence)


class ExplodingRouter:
    def extract(self, source: BytesIO) -> ExtractionBundle:
        del source
        raise RuntimeError("synthetic extraction failure")


def _table_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            name: int(connection.scalar(select(func.count()).select_from(table)) or 0)
            for name, table in metadata.tables.items()
        }


def _build_orchestrator(
    *,
    engine: Engine,
    httpserver: HTTPServer,
    blob_root: Path,
    router: LowConfidenceRouter | ExplodingRouter,
) -> RunOrchestrator:
    index_url = httpserver.url_for("/index")
    client = ResponsibleHttpClient(
        HttpClientConfig(
            user_agent="BenterPeru/0.1 contacto@example.invalid",
            max_attempts=2,
            min_request_interval_seconds=0.0,
        )
    )
    source = SourceDefinition(
        code="informativo",
        name="El Informativo Hipico",
        base_url=httpserver.url_for("/"),
        index_url=index_url,
    )
    return RunOrchestrator(
        engine=engine,
        sources={source.code: source},
        policy_gate=PolicyGate(client),
        http_client=client,
        blob_store=LocalBlobStore(blob_root),
        extraction_router=router,
        review_threshold=0.8,
    )


def test_complete_pipeline_is_auditable_and_idempotent(
    migrated_engine: Engine,
    httpserver: HTTPServer,
    tmp_path: Path,
) -> None:
    pdf = _pdf_bytes()
    document_url = httpserver.url_for("/opaque-document")
    html = (
        '<a data-document-type="estudie_su_polla" href="/opaque-document">'
        "Edicion semanal</a>"
    )
    httpserver.expect_request("/robots.txt").respond_with_data(
        "User-agent: *\nAllow: /\n", content_type="text/plain"
    )
    httpserver.expect_request("/index").respond_with_data(html, content_type="text/html")
    httpserver.expect_request("/opaque-document").respond_with_data(
        pdf, content_type="application/pdf"
    )
    router = LowConfidenceRouter()
    orchestrator = _build_orchestrator(
        engine=migrated_engine,
        httpserver=httpserver,
        blob_root=tmp_path.parent / f"{tmp_path.name}-blobs",
        router=router,
    )

    first = orchestrator.run(source_code="informativo", correlation_id="run-001")
    first_counts = _table_counts(migrated_engine)
    second = orchestrator.run(source_code="informativo", correlation_id="run-002")
    second_counts = _table_counts(migrated_engine)

    assert first.status == "completed_with_reviews"
    assert first.downloaded_count == 1
    assert first.fact_count >= 1
    assert first.review_count == first.fact_count
    assert second.status == "completed"
    assert second.deduplicated_count == 1
    assert router.calls == 1
    assert set(inspect(migrated_engine).get_table_names()) - {"alembic_version"} == set(
        metadata.tables
    )
    assert first_counts["documents"] == 1
    assert first_counts["document_versions"] == 1
    assert first_counts["processing_tasks"] == 1
    assert first_counts["extraction_runs"] == 1
    assert first_counts["extracted_facts"] == first.fact_count
    assert first_counts["fact_evidence"] == first.fact_count
    assert first_counts["review_items"] == first.fact_count
    for stable_table in (
        "blob_objects",
        "publications",
        "publication_versions",
        "documents",
        "publication_document_links",
        "document_versions",
        "processing_tasks",
        "extraction_runs",
        "extracted_facts",
        "fact_evidence",
        "review_items",
    ):
        assert second_counts[stable_table] == first_counts[stable_table]
    assert second_counts["crawl_runs"] == 2
    assert second_counts["run_reports"] == 2
    assert second_counts["run_metrics"] == 12
    assert (tmp_path.parent / f"{tmp_path.name}-blobs" / sha256(pdf).hexdigest()).is_file()
    assert document_url.endswith("/opaque-document")


def test_pipeline_exception_rolls_back_all_database_records(
    migrated_engine: Engine,
    httpserver: HTTPServer,
    tmp_path: Path,
) -> None:
    pdf = _pdf_bytes()
    html = '<a data-document-type="programa" href="/document">Programa</a>'
    httpserver.expect_request("/robots.txt").respond_with_data("User-agent: *\nAllow: /\n")
    httpserver.expect_request("/index").respond_with_data(html)
    httpserver.expect_request("/document").respond_with_data(
        pdf, content_type="application/pdf"
    )
    blob_root = tmp_path.parent / f"{tmp_path.name}-rollback-blobs"
    orchestrator = _build_orchestrator(
        engine=migrated_engine,
        httpserver=httpserver,
        blob_root=blob_root,
        router=ExplodingRouter(),
    )

    with pytest.raises(RuntimeError, match="synthetic extraction failure"):
        orchestrator.run(source_code="informativo", correlation_id="run-failure")

    assert all(count == 0 for count in _table_counts(migrated_engine).values())
    assert (blob_root / sha256(pdf).hexdigest()).is_file()
