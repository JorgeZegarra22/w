"""End-to-end local-file CLI test with no network dependency."""

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from benter_peru.cli import main


def _write_program(path: Path) -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(35, 790, "1ra. CAR.- HANDICAP")
    canvas.drawString(35, 750, "1")
    canvas.drawString(55, 750, "WAYTT")
    canvas.drawString(173, 750, "56.00 / 53")
    canvas.drawString(260, 750, "S.B.P.")
    canvas.drawString(342, 750, "J H SUAREZ")
    canvas.drawString(405, 750, "R Melgarejo")
    canvas.drawString(35, 710, "2da. CAR.- SIGUIENTE")
    canvas.save()
    content = stream.getvalue()
    path.write_bytes(content)
    return content


def test_cli_local_file_persists_blob_and_structured_fact_without_http(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pdf_path = tmp_path / "program.pdf"
    content = _write_program(pdf_path)
    database_path = tmp_path / "local.sqlite3"
    blob_root = tmp_path.parent / f"{tmp_path.name}-local-blobs"
    environment = {
        "BENTER_SOURCE_URL": "https://network-must-not-be-used.invalid/",
        "BENTER_USER_AGENT": "BenterPeruBot/1.0 (+https://github.com/example/hipico)",
        "BENTER_DATABASE_PATH": str(database_path),
        "BENTER_BLOB_ROOT": str(blob_root),
        "BENTER_MIN_REQUEST_INTERVAL_SECONDS": "0",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    exit_code = main(
        [
            "run",
            "--source",
            "elinformativohipico",
            "--local-file",
            str(pdf_path),
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["documents"][0]["sha256"] == sha256(content).hexdigest()
    assert report["documents"][0]["processing_status"] == "extracted"
    assert report["fact_count"] == 1
    assert report["evidence_count"] == 1
    assert (blob_root / sha256(content).hexdigest()).is_file()
