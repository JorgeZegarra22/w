"""Entity resolver integration tests over deterministic extracted facts."""

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select

from benter_peru.cli import _run
from benter_peru.config import RuntimeConfig
from benter_peru.db.engine import create_database_engine
from benter_peru.db.schema import horses, jockeys, race_entries, races
from benter_peru.entities.resolver import EntityResolver


def _write_program(path: Path) -> str:
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(35, 830, "REUNION 202647")
    canvas.drawString(35, 815, "SABADO 21 DE NOVIEMBRE 2026")
    canvas.drawString(35, 790, "1ra. CAR.- DISTANCIA 1,000 METROS ARENA")
    rows = (
        (750, "1", "WAYTT", "56.00 / 53", "S.B.P.", "J H SUAREZ", "R MELGAREJO"),
        (710, "2", "tNrzrAMo (usA)", "55.00 / 52", "MYRNA", "J. H. Suarez", "A DIAZ"),
    )
    for y, mandil, horse, weight, stud, jockey, trainer in rows:
        canvas.drawString(35, y, mandil)
        canvas.drawString(55, y, horse)
        canvas.drawString(173, y, weight)
        canvas.drawString(260, y, stud)
        canvas.drawString(342, y, jockey)
        canvas.drawString(405, y, trainer)
    canvas.drawString(35, 670, "2da. CAR.- SIGUIENTE")
    canvas.save()
    content = stream.getvalue()
    path.write_bytes(content)
    from hashlib import sha256

    return sha256(content).hexdigest()


def test_resolver_creates_safe_entities_and_is_idempotent(tmp_path: Path) -> None:
    pdf_path = tmp_path / "program.pdf"
    sha = _write_program(pdf_path)
    config = RuntimeConfig(
        source_url="https://network-must-not-be-used.invalid/",
        user_agent="BenterPeruBot/1.0 (+https://github.com/example/hipico)",
        database_path=tmp_path / "entities.sqlite3",
        blob_root=tmp_path / "blobs",
        min_request_interval_seconds=0,
    )
    _run(config, local_file=pdf_path)
    engine = create_database_engine(config.database_url)
    try:
        first = EntityResolver(engine).resolve_sha(sha)
        second = EntityResolver(engine).resolve_sha(sha)

        assert first.races_created == 1
        assert first.entries_created == 2
        assert first.horses_created == 2
        assert first.jockeys_created == 1
        assert first.jockeys_reused == 1
        assert first.unconfirmed_horses == 1
        assert second.races_reused == 1
        assert second.entries_reused == 2
        assert second.entries_created == 0

        with engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(races)) == 1
            assert connection.scalar(select(func.count()).select_from(race_entries)) == 2
            assert connection.scalar(select(func.count()).select_from(jockeys)) == 1
            horse_rows = connection.execute(
                select(horses.c.canonical_name, horses.c.confirmation_status).order_by(
                    horses.c.canonical_name
                )
            ).all()
        assert horse_rows == [("WAYTT", "confirmed"), ("tNrzrAMo (usA)", "unconfirmed")]
    finally:
        engine.dispose()
