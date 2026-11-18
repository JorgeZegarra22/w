"""Command-line entry point for controlled, auditable source runs."""

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from benter_peru.config import RuntimeConfig
from benter_peru.db.engine import create_database_engine
from benter_peru.db.migrations import upgrade_database
from benter_peru.db.schema import (
    document_versions,
    documents,
    extracted_facts,
    extraction_runs,
    fact_evidence,
)
from benter_peru.discovery import HtmlDocumentDiscoverer, SourceDefinition
from benter_peru.entities.resolver import EntityResolver
from benter_peru.extraction.identity import EXTRACTOR_NAME, EXTRACTOR_VERSION
from benter_peru.extraction.router import ExtractionRouter
from benter_peru.history.importer import HistoryImporter
from benter_peru.http.client import HttpClientConfig, ResponsibleHttpClient
from benter_peru.ids import new_ulid
from benter_peru.orchestrator import RunOrchestrator, RunResult
from benter_peru.policy import PolicyGate
from benter_peru.storage.local import LocalBlobStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benter")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run one configured source")
    run.add_argument("--source", required=True, choices=("elinformativohipico",))
    run.add_argument("--local-file", type=Path)
    resolve = subcommands.add_parser("resolve", help="resolve extracted facts into entities")
    resolve.add_argument("--sha", required=True)
    history = subcommands.add_parser("history", help="manage historical race results")
    history_commands = history.add_subparsers(dest="history_command", required=True)
    history_import = history_commands.add_parser("import", help="import a strict CSV file")
    history_import.add_argument("--file", type=Path, required=True)
    return parser


def _source_definition(config: RuntimeConfig) -> SourceDefinition:
    parsed = urlsplit(config.source_url)
    base_url = urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))
    return SourceDefinition(
        code="elinformativohipico",
        name="El Informativo Hipico",
        base_url=base_url,
        index_url=config.source_url,
        rate_limit_ms=int(config.min_request_interval_seconds * 1000),
    )


def _build_report(engine: Engine, result: RunResult) -> dict[str, Any]:
    local_sha = next(
        (
            item.url.removeprefix("local://sha256/")
            for item in result.discovered_documents
            if item.url.startswith("local://sha256/")
        ),
        None,
    )
    document_filter = (
        document_versions.c.blob_sha256 == local_sha
        if local_sha is not None
        else document_versions.c.crawl_run_id == result.crawl_run_id
    )
    fact_filter = document_filter
    if local_sha is not None:
        fact_filter = (
            document_filter
            & (extraction_runs.c.extractor_name == EXTRACTOR_NAME)
            & (extraction_runs.c.extractor_version == EXTRACTOR_VERSION)
        )
    document_query = (
        select(
            documents.c.canonical_url,
            documents.c.document_type,
            document_versions.c.blob_sha256,
            document_versions.c.processing_status,
        )
        .join(document_versions, document_versions.c.document_id == documents.c.id)
        .where(document_filter)
    )
    fact_query = (
        select(func.count())
        .select_from(extracted_facts)
        .join(extraction_runs, extraction_runs.c.id == extracted_facts.c.extraction_run_id)
        .join(
            document_versions,
            document_versions.c.id == extraction_runs.c.document_version_id,
        )
        .where(fact_filter)
    )
    evidence_query = (
        select(func.count())
        .select_from(fact_evidence)
        .join(extracted_facts, extracted_facts.c.id == fact_evidence.c.fact_id)
        .join(extraction_runs, extraction_runs.c.id == extracted_facts.c.extraction_run_id)
        .join(
            document_versions,
            document_versions.c.id == extraction_runs.c.document_version_id,
        )
        .where(fact_filter)
    )
    with engine.connect() as connection:
        rows = connection.execute(document_query).mappings().all()
        fact_count = int(connection.scalar(fact_query) or 0)
        evidence_count = int(connection.scalar(evidence_query) or 0)

    return {
        "crawl_run_id": result.crawl_run_id,
        "status": result.status,
        "discovered": [
            {"url": item.url, "document_type": item.document_type}
            for item in result.discovered_documents
        ],
        "documents": [
            {
                "url": row["canonical_url"],
                "document_type": row["document_type"],
                "sha256": row["blob_sha256"],
                "processing_status": row["processing_status"],
                "requires_ocr": row["processing_status"] == "needs_ocr",
            }
            for row in rows
        ],
        "fact_count": fact_count,
        "evidence_count": evidence_count,
        "failure_count": result.failure_count,
    }


def _run(config: RuntimeConfig, *, local_file: Path | None = None) -> dict[str, Any]:
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    source = _source_definition(config)
    engine = create_database_engine(config.database_url)
    try:
        upgrade_database(engine)
        client = None
        policy_gate = None
        discoverer = None
        if local_file is None:
            client = ResponsibleHttpClient(
                HttpClientConfig(
                    user_agent=config.user_agent,
                    max_attempts=config.http_max_attempts,
                    min_request_interval_seconds=config.min_request_interval_seconds,
                )
            )
            policy_gate = PolicyGate(client)
            discoverer = HtmlDocumentDiscoverer(expected_types=("estudie_su_polla",))
        orchestrator = RunOrchestrator(
            engine=engine,
            sources={source.code: source},
            policy_gate=policy_gate,
            http_client=client,
            blob_store=LocalBlobStore(config.blob_root),
            extraction_router=ExtractionRouter(),
            discoverer=discoverer,
            review_threshold=config.review_confidence_threshold,
        )
        if local_file is None:
            result = orchestrator.run(source_code=source.code, correlation_id=new_ulid())
        else:
            result = orchestrator.run_local(
                source_code=source.code,
                correlation_id=new_ulid(),
                file_path=local_file,
            )
        return _build_report(engine, result)
    finally:
        engine.dispose()


def _resolve(config: RuntimeConfig, sha256: str) -> dict[str, Any]:
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(config.database_url)
    try:
        upgrade_database(engine)
        return asdict(EntityResolver(engine).resolve_sha(sha256))
    finally:
        engine.dispose()


def _import_history(config: RuntimeConfig, path: Path) -> dict[str, Any]:
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(config.database_url)
    try:
        upgrade_database(engine)
        return asdict(HistoryImporter(engine).import_csv(path))
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    if arguments.command == "run":
        report = _run(RuntimeConfig.from_env(), local_file=arguments.local_file)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if arguments.command == "resolve":
        report = _resolve(RuntimeConfig.from_env(), arguments.sha)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if arguments.command == "history" and arguments.history_command == "import":
        report = _import_history(RuntimeConfig.from_env(), arguments.file)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    raise AssertionError("unreachable command")


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    raise SystemExit(main())
