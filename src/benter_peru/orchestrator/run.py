"""Atomic, auditable document collection and extraction orchestration."""

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from typing import Protocol, cast
from urllib.parse import urlsplit

import httpx
from sqlalchemy import and_, insert, select, update
from sqlalchemy.engine import Connection, Engine

from benter_peru.db.schema import (
    blob_objects,
    crawl_runs,
    document_versions,
    documents,
    extracted_facts,
    extraction_runs,
    fact_evidence,
    fetch_attempts,
    processing_tasks,
    publication_document_links,
    publication_versions,
    publications,
    review_items,
    run_metrics,
    run_reports,
    source_checkpoints,
    source_policy_snapshots,
    source_registry,
)
from benter_peru.db.uow import UnitOfWork
from benter_peru.discovery import DiscoveredDocument, HtmlDocumentDiscoverer, SourceDefinition
from benter_peru.extraction.models import ExtractionBundle
from benter_peru.http.client import ResponsibleHttpClient
from benter_peru.ids import new_ulid
from benter_peru.orchestrator.models import RunResult, RunStatus
from benter_peru.policy import PolicyDecision, PolicyGate
from benter_peru.storage.local import LocalBlobStore

LOGGER = logging.getLogger(__name__)


class ExtractionAdapter(Protocol):
    def extract(self, source: BytesIO) -> ExtractionBundle: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RunOrchestrator:
    """Execute the approved Entregable 1 pipeline as one database transaction."""

    def __init__(
        self,
        *,
        engine: Engine,
        sources: Mapping[str, SourceDefinition],
        policy_gate: PolicyGate,
        http_client: ResponsibleHttpClient,
        blob_store: LocalBlobStore,
        extraction_router: ExtractionAdapter,
        discoverer: HtmlDocumentDiscoverer | None = None,
        review_threshold: float = 0.8,
        id_factory: Callable[[], str] = new_ulid,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not 0 <= review_threshold <= 1:
            raise ValueError("review_threshold must be between zero and one")
        self._engine = engine
        self._sources = dict(sources)
        self._policy_gate = policy_gate
        self._http_client = http_client
        self._blob_store = blob_store
        self._extraction_router = extraction_router
        self._discoverer = discoverer or HtmlDocumentDiscoverer()
        self._review_threshold = review_threshold
        self._id = id_factory
        self._clock = clock

    def run(self, *, source_code: str, correlation_id: str) -> RunResult:
        """Run one source; exceptions roll every database write back together."""
        if not correlation_id.strip():
            raise ValueError("correlation_id must be nonempty")
        try:
            source = self._sources[source_code]
        except KeyError as exc:
            raise ValueError(f"unknown source_code: {source_code}") from exc

        with UnitOfWork(self._engine) as uow:
            connection = uow.connection
            source_id = self._get_or_create_source(connection, source)
            previous = self._existing_result(connection, correlation_id)
            if previous is not None:
                return previous

            run_id = self._id()
            started_at = self._clock()
            connection.execute(
                insert(crawl_runs).values(
                    id=run_id,
                    source_id=source_id,
                    correlation_id=correlation_id,
                    status="running",
                    started_at=started_at,
                )
            )

            index_policy = self._evaluate_policy(connection, source_id, source.index_url)
            if not index_policy.allowed:
                return self._finish(
                    connection,
                    run_id=run_id,
                    source_id=source_id,
                    status="deferred",
                    discovered=0,
                    downloaded=0,
                    deduplicated=0,
                    facts=0,
                    reviews=0,
                    failures=0,
                    discovered_documents=(),
                )

            index_response = self._fetch(connection, run_id, source.index_url)
            index_response.raise_for_status()
            publication_id, publication_version_id = self._record_publication(
                connection,
                source_id=source_id,
                run_id=run_id,
                source=source,
                content=index_response.content,
            )
            del publication_id
            discovered = self._discoverer.discover(index_response.text, source.index_url)
            downloaded_count = 0
            deduplicated_count = 0
            fact_count = 0
            review_count = 0
            failure_count = 0

            for item in discovered:
                fetch_url = item.download_url or item.url
                policy = self._evaluate_policy(connection, source_id, fetch_url)
                if not policy.allowed:
                    continue
                response = self._fetch(connection, run_id, fetch_url)
                response.raise_for_status()
                downloaded_count += 1
                content = response.content
                if b"%PDF-" not in content[:1024]:
                    failure_count += 1
                    LOGGER.warning(
                        "document response is not a PDF: %s",
                        item.url,
                        extra={
                            "document_type": item.document_type,
                            "fetch_url": fetch_url,
                            "content_type": response.headers.get("Content-Type"),
                        },
                    )
                    continue
                digest = sha256(content).hexdigest()
                stored = self._blob_store.put_if_absent(BytesIO(content), digest)
                self._record_blob(connection, stored.storage_key, digest, stored.byte_size)
                document_id, version_id = self._record_document(
                    connection,
                    source_id=source_id,
                    run_id=run_id,
                    publication_version_id=publication_version_id,
                    url=item.url,
                    document_type=item.document_type,
                    link_context=item.link_context,
                    blob_sha256=digest,
                )
                del document_id
                input_fingerprint = sha256(
                    f"{digest}:pdf-text:1".encode()
                ).hexdigest()
                existing_task = connection.execute(
                    select(processing_tasks.c.status).where(
                        processing_tasks.c.idempotency_key == input_fingerprint
                    )
                ).first()
                if existing_task is not None and existing_task.status == "completed":
                    deduplicated_count += 1
                    continue

                task_id = self._id()
                connection.execute(
                    insert(processing_tasks).values(
                        id=task_id,
                        crawl_run_id=run_id,
                        document_version_id=version_id,
                        idempotency_key=input_fingerprint,
                        task_type="extract_pdf_text",
                        status="running",
                        attempt_count=1,
                    )
                )
                connection.execute(
                    update(document_versions)
                    .where(document_versions.c.id == version_id)
                    .values(processing_status="extracting")
                )
                extraction_id = self._id()
                connection.execute(
                    insert(extraction_runs).values(
                        id=extraction_id,
                        document_version_id=version_id,
                        input_fingerprint=input_fingerprint,
                        extractor_name="pdfplumber-text",
                        extractor_version="1",
                        method="text",
                        status="running",
                    )
                )
                bundle = self._extraction_router.extract(BytesIO(content))
                if bundle.requires_ocr:
                    connection.execute(
                        update(extraction_runs)
                        .where(extraction_runs.c.id == extraction_id)
                        .values(status="needs_ocr")
                    )
                    connection.execute(
                        update(document_versions)
                        .where(document_versions.c.id == version_id)
                        .values(processing_status="needs_ocr")
                    )
                else:
                    created_facts, created_reviews = self._record_facts(
                        connection,
                        extraction_id=extraction_id,
                        input_fingerprint=input_fingerprint,
                        bundle=bundle,
                    )
                    fact_count += created_facts
                    review_count += created_reviews
                    connection.execute(
                        update(extraction_runs)
                        .where(extraction_runs.c.id == extraction_id)
                        .values(status="completed")
                    )
                    connection.execute(
                        update(document_versions)
                        .where(document_versions.c.id == version_id)
                        .values(processing_status="extracted")
                    )
                connection.execute(
                    update(processing_tasks)
                    .where(processing_tasks.c.id == task_id)
                    .values(status="completed")
                )

            status: RunStatus
            if failure_count:
                status = "partial_failure"
            elif review_count:
                status = "completed_with_reviews"
            else:
                status = "completed"
            return self._finish(
                connection,
                run_id=run_id,
                source_id=source_id,
                status=status,
                discovered=len(discovered),
                downloaded=downloaded_count,
                deduplicated=deduplicated_count,
                facts=fact_count,
                reviews=review_count,
                failures=failure_count,
                discovered_documents=discovered,
            )

    def _get_or_create_source(
        self, connection: Connection, source: SourceDefinition
    ) -> str:
        existing = connection.scalar(
            select(source_registry.c.id).where(source_registry.c.code == source.code)
        )
        if existing is not None:
            return cast(str, existing)
        source_id = self._id()
        connection.execute(
            insert(source_registry).values(
                id=source_id,
                code=source.code,
                name=source.name,
                base_url=source.base_url,
                rate_limit_ms=source.rate_limit_ms,
                enabled=True,
            )
        )
        return source_id

    def _existing_result(
        self, connection: Connection, correlation_id: str
    ) -> RunResult | None:
        row = connection.execute(
            select(crawl_runs.c.id, run_reports)
            .join(run_reports, run_reports.c.crawl_run_id == crawl_runs.c.id)
            .where(crawl_runs.c.correlation_id == correlation_id)
        ).mappings().first()
        if row is None:
            return None
        return RunResult(
            crawl_run_id=cast(str, row["id"]),
            status=cast(RunStatus, row["status"]),
            discovered_count=row["discovered_count"],
            downloaded_count=row["downloaded_count"],
            deduplicated_count=row["deduplicated_count"],
            fact_count=row["fact_count"],
            review_count=row["review_count"],
            failure_count=row["failure_count"],
            discovered_documents=(),
        )

    def _evaluate_policy(
        self, connection: Connection, source_id: str, url: str
    ) -> PolicyDecision:
        decision = self._policy_gate.evaluate(url)
        status = "allowed" if decision.allowed else "denied"
        connection.execute(
            insert(source_policy_snapshots).values(
                id=self._id(),
                source_id=source_id,
                robots_sha256=decision.robots_sha256,
                fetched_at=self._clock(),
                crawl_allowed=decision.allowed,
                policy_status=status,
            )
        )
        return decision

    def _fetch(self, connection: Connection, run_id: str, url: str) -> httpx.Response:
        response = self._http_client.fetch(url)
        attempt = int(response.extensions.get("benter_attempt_count", 1))
        outcome = "success" if 200 <= response.status_code < 300 else "permanent_error"
        connection.execute(
            insert(fetch_attempts).values(
                id=self._id(),
                crawl_run_id=run_id,
                url=url,
                attempt_no=attempt,
                response_status=response.status_code,
                outcome=outcome,
            )
        )
        return response

    def _record_publication(
        self,
        connection: Connection,
        *,
        source_id: str,
        run_id: str,
        source: SourceDefinition,
        content: bytes,
    ) -> tuple[str, str]:
        now = self._clock()
        publication_id = connection.scalar(
            select(publications.c.id).where(
                and_(
                    publications.c.source_id == source_id,
                    publications.c.canonical_url == source.index_url,
                )
            )
        )
        if publication_id is None:
            publication_id = self._id()
            connection.execute(
                insert(publications).values(
                    id=publication_id,
                    source_id=source_id,
                    canonical_url=source.index_url,
                    publication_type="document_index",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            connection.execute(
                update(publications)
                .where(publications.c.id == publication_id)
                .values(last_seen_at=now)
            )
        content_hash = sha256(content).hexdigest()
        version_id = connection.scalar(
            select(publication_versions.c.id).where(
                and_(
                    publication_versions.c.publication_id == publication_id,
                    publication_versions.c.content_sha256 == content_hash,
                )
            )
        )
        if version_id is None:
            version_id = self._id()
            connection.execute(
                insert(publication_versions).values(
                    id=version_id,
                    publication_id=publication_id,
                    crawl_run_id=run_id,
                    content_sha256=content_hash,
                    detected_at=now,
                )
            )
        return cast(str, publication_id), cast(str, version_id)

    def _record_blob(
        self, connection: Connection, storage_key: str, digest: str, byte_size: int
    ) -> None:
        if connection.scalar(
            select(blob_objects.c.sha256).where(blob_objects.c.sha256 == digest)
        ) is None:
            connection.execute(
                insert(blob_objects).values(
                    sha256=digest,
                    byte_size=byte_size,
                    media_type="application/pdf",
                    storage_key=storage_key,
                    first_stored_at=self._clock(),
                    retained_locally=True,
                )
            )

    def _record_document(
        self,
        connection: Connection,
        *,
        source_id: str,
        run_id: str,
        publication_version_id: str,
        url: str,
        document_type: str,
        link_context: str,
        blob_sha256: str,
    ) -> tuple[str, str]:
        now = self._clock()
        document_id = connection.scalar(
            select(documents.c.id).where(
                and_(documents.c.source_id == source_id, documents.c.canonical_url == url)
            )
        )
        if document_id is None:
            document_id = self._id()
            connection.execute(
                insert(documents).values(
                    id=document_id,
                    source_id=source_id,
                    canonical_url=url,
                    document_type=document_type,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            connection.execute(
                update(documents)
                .where(documents.c.id == document_id)
                .values(last_seen_at=now)
            )
        version_id = connection.scalar(
            select(document_versions.c.id).where(
                and_(
                    document_versions.c.document_id == document_id,
                    document_versions.c.blob_sha256 == blob_sha256,
                )
            )
        )
        if version_id is None:
            version_id = self._id()
            filename = PurePosixPath(urlsplit(url).path).name or None
            connection.execute(
                insert(document_versions).values(
                    id=version_id,
                    document_id=document_id,
                    blob_sha256=blob_sha256,
                    crawl_run_id=run_id,
                    original_filename=filename,
                    detected_at=now,
                    downloaded_at=now,
                    processing_status="pending",
                )
            )
        link_exists = connection.scalar(
            select(publication_document_links.c.id).where(
                and_(
                    publication_document_links.c.publication_version_id
                    == publication_version_id,
                    publication_document_links.c.document_id == document_id,
                    publication_document_links.c.discovered_url == url,
                )
            )
        )
        if link_exists is None:
            connection.execute(
                insert(publication_document_links).values(
                    id=self._id(),
                    publication_version_id=publication_version_id,
                    document_id=document_id,
                    discovered_url=url,
                    link_context=link_context,
                    discovery_method="html",
                )
            )
        return cast(str, document_id), cast(str, version_id)

    def _record_facts(
        self,
        connection: Connection,
        *,
        extraction_id: str,
        input_fingerprint: str,
        bundle: ExtractionBundle,
    ) -> tuple[int, int]:
        review_count = 0
        for index, evidence in enumerate(bundle.evidence):
            fingerprint = sha256(
                f"{input_fingerprint}:{index}:{evidence.page_number}:{evidence.text}".encode()
            ).hexdigest()
            fact_id = self._id()
            requires_review = (
                evidence.requires_review or evidence.confidence < self._review_threshold
            )
            connection.execute(
                insert(extracted_facts).values(
                    id=fact_id,
                    extraction_run_id=extraction_id,
                    fact_fingerprint=fingerprint,
                    fact_type="pdf_text",
                    subject_key=f"page:{evidence.page_number}:word:{index}",
                    normalized_value=evidence.text.strip(),
                    raw_value=evidence.text,
                    confidence=evidence.confidence,
                    requires_review=requires_review,
                )
            )
            connection.execute(
                insert(fact_evidence).values(
                    id=self._id(),
                    fact_id=fact_id,
                    page_number=evidence.page_number,
                    bbox_x0=evidence.bbox.x0,
                    bbox_y0=evidence.bbox.top,
                    bbox_x1=evidence.bbox.x1,
                    bbox_y1=evidence.bbox.bottom,
                    snippet=evidence.text[:500],
                    extraction_method=evidence.method,
                )
            )
            if requires_review:
                review_count += 1
                reason = "extractor_flagged" if evidence.requires_review else "low_confidence"
                connection.execute(
                    insert(review_items).values(
                        id=self._id(),
                        fact_id=fact_id,
                        status="pending",
                        reason_code=reason,
                        created_at=self._clock(),
                    )
                )
        return len(bundle.evidence), review_count

    def _finish(
        self,
        connection: Connection,
        *,
        run_id: str,
        source_id: str,
        status: RunStatus,
        discovered: int,
        downloaded: int,
        deduplicated: int,
        facts: int,
        reviews: int,
        failures: int,
        discovered_documents: tuple[DiscoveredDocument, ...],
    ) -> RunResult:
        finished_at = self._clock()
        connection.execute(
            update(crawl_runs)
            .where(crawl_runs.c.id == run_id)
            .values(status=status, finished_at=finished_at)
        )
        report_id = self._id()
        values = {
            "discovered_count": discovered,
            "downloaded_count": downloaded,
            "deduplicated_count": deduplicated,
            "fact_count": facts,
            "review_count": reviews,
            "failure_count": failures,
        }
        connection.execute(
            insert(run_reports).values(
                id=report_id,
                crawl_run_id=run_id,
                status=status,
                **values,
            )
        )
        connection.execute(
            insert(run_metrics),
            [
                {
                    "id": self._id(),
                    "run_report_id": report_id,
                    "metric_name": name,
                    "metric_value": value,
                }
                for name, value in values.items()
            ],
        )
        checkpoint = connection.execute(
            select(source_checkpoints.c.id).where(
                and_(
                    source_checkpoints.c.source_id == source_id,
                    source_checkpoints.c.checkpoint_key == "last_completed_run",
                )
            )
        ).scalar_one_or_none()
        if checkpoint is None:
            connection.execute(
                insert(source_checkpoints).values(
                    id=self._id(),
                    source_id=source_id,
                    checkpoint_key="last_completed_run",
                    checkpoint_value=run_id,
                    last_success_at=finished_at,
                )
            )
        else:
            connection.execute(
                update(source_checkpoints)
                .where(source_checkpoints.c.id == checkpoint)
                .values(checkpoint_value=run_id, last_success_at=finished_at)
            )
        return RunResult(
            crawl_run_id=run_id,
            status=status,
            discovered_count=discovered,
            downloaded_count=downloaded,
            deduplicated_count=deduplicated,
            fact_count=facts,
            review_count=reviews,
            failure_count=failures,
            discovered_documents=discovered_documents,
        )
