"""Transactional materialization of journalist-pick facts."""

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import journalist_picks
from benter_peru.discovery import SourceDefinition
from benter_peru.entities.journalist_picks import JournalistPickResolver
from benter_peru.extraction.router import ExtractionRouter
from benter_peru.orchestrator import RunOrchestrator
from benter_peru.storage.local import LocalBlobStore


def _write_magazine(path: Path) -> None:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=letter)
    canvas.drawString(60, 740, "REUNION 202647")
    canvas.drawString(60, 716, "PRONOSTICO DE LA REVISTA")
    canvas.drawString(60, 692, "1 | ESTUDIE SU POLLA | 3 MR. PEGGY, SHOTRA")
    canvas.save()
    path.write_bytes(stream.getvalue())


def test_materializes_confirmed_and_review_picks_idempotently(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    path = tmp_path / "revista.pdf"
    _write_magazine(path)
    source = SourceDefinition(
        "informativo",
        "Informativo",
        "https://example.test/",
        "https://example.test/",
        0,
    )
    orchestrator = RunOrchestrator(
        engine=migrated_engine,
        sources={source.code: source},
        policy_gate=None,
        http_client=None,
        blob_store=LocalBlobStore(tmp_path / "blobs"),
        extraction_router=ExtractionRouter(),
    )
    result = orchestrator.run_local(
        source_code=source.code,
        correlation_id="magazine-run",
        file_path=path,
        document_type="estudie_su_polla",
    )
    sha = result.discovered_documents[0].url.removeprefix("local://sha256/")

    first = JournalistPickResolver(migrated_engine).resolve_sha(sha)
    second = JournalistPickResolver(migrated_engine).resolve_sha(sha)

    assert (first.created, first.reused, first.requires_review) == (2, 0, 1)
    assert (second.created, second.reused) == (0, 2)
    with migrated_engine.connect() as connection:
        rows = connection.execute(
            select(journalist_picks).order_by(journalist_picks.c.selection_rank)
        ).mappings().all()
        assert connection.scalar(select(func.count()).select_from(journalist_picks)) == 2
    assert rows[0]["mandil"] == 3
    assert rows[0]["requires_review"] is False
    assert rows[1]["mandil"] is None
    assert rows[1]["requires_review"] is True
