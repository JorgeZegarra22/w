"""CLI integration contract using real adapters and a local source server."""

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from pytest_httpserver import HTTPServer
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from benter_peru.cli import main


def _pdf_bytes() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=letter)
    canvas.drawString(72, 720, "Programa Hipico Real")
    canvas.save()
    return stream.getvalue()


def test_cli_runs_pipeline_and_reports_persisted_pdf_facts(
    httpserver: HTTPServer,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pdf = _pdf_bytes()
    httpserver.expect_request("/robots.txt").respond_with_data("User-agent: *\nAllow: /\n")
    httpserver.expect_request("/").respond_with_data(
        '<a href="/program-source">PROG-MONTERRICO</a>', content_type="text/html"
    )
    httpserver.expect_request("/program-source").respond_with_data(
        pdf, content_type="application/pdf"
    )
    database_path = tmp_path / "real.sqlite3"
    blob_root = tmp_path.parent / f"{tmp_path.name}-real-blobs"
    environment = {
        "BENTER_SOURCE_URL": httpserver.url_for("/"),
        "BENTER_USER_AGENT": "BenterPeruBot/1.0 (+https://github.com/example/hipico)",
        "BENTER_DATABASE_PATH": str(database_path),
        "BENTER_BLOB_ROOT": str(blob_root),
        "BENTER_MIN_REQUEST_INTERVAL_SECONDS": "0",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    exit_code = main(["run", "--source", "elinformativohipico"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["discovered"] == [
        {
            "document_type": "programa_monterrico",
            "url": httpserver.url_for("/program-source"),
        }
    ]
    assert report["documents"][0]["sha256"] == sha256(pdf).hexdigest()
    assert report["documents"][0]["processing_status"] == "extracted"
    assert report["documents"][0]["requires_ocr"] is False
    assert report["fact_count"] >= 1
    assert report["evidence_count"] == report["fact_count"]
    assert (blob_root / sha256(pdf).hexdigest()).is_file()
    assert "estudie_su_polla" in captured.err
