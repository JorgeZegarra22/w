from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from benter_peru.db.schema import horse_stats_snapshots, race_entries, races
from benter_peru.scrapers.official_scraper import (
    OfficialProgramError,
    discover_race_urls,
    parse_program,
)
from benter_peru.scrapers.official_store import persist_programs
from benter_peru.storage.local import LocalBlobStore

URL = "https://hipodromodemonterrico.com.pe/monterrico/programa?carrera=12"


def test_only_official_program_links_are_discovered() -> None:
    document = """
    <a href="/monterrico/programa?carrera=12">1ª</a>
    <a href="/monterrico/programa?carrera=12">1ª</a>
    <a href="/monterrico/resultado?carrera=13">Resultado</a>
    <a href="https://example.test/monterrico/programa?carrera=14">Externo</a>
    """
    assert discover_race_urls(document) == (URL,)


@pytest.fixture
def program_html() -> str:
    return """
    <section>
      <div><p>Reunión 21, Hipódromo de Monterrico | 2026-11-21</p></div>
      <div><span>1ª</span><span>13:30 hrs.</span><span>1000m</span><span>Arena</span></div>
      <div><div class="border-2 rounded-lg overflow-hidden">
        <div><div><span>4</span><span>P2</span></div><div>
          <div><span><a>Ejemplar A</a></span><span>56k</span></div>
          <div>MC 5 Stud Ejemplo</div>
          <div><span>Jinete</span> A Jinete<span>5-1</span></div>
          <div><span>Preparador</span> B Preparador<span>5-2</span></div>
          <table><tbody><tr><td>Total</td><td>11</td><td>3</td><td>2</td><td>1</td>
            <td>0</td><td>5</td><td>PEN $4.000</td></tr></tbody></table>
        </div></div>
        <div><table><tbody><tr><td><a>21Oct26</a></td><td>MONT</td><td>1000m</td>
          <td>0.52.88</td><td></td><td></td><td>1°/6</td><td></td><td></td>
          <td></td><td></td><td></td><td></td><td>Por dos cuerpos</td></tr></tbody></table></div>
        <div><span>Aprontes</span><span><span>18Nov26</span> MONT 400m A Jinete
          <span class="font-mono">0.23.2/5</span></span></div>
      </div></div>
    </section>
    """


def test_desktop_card_keeps_finish_time_and_workout_precision(program_html: str) -> None:
    program = parse_program(program_html, URL)
    assert (program.race_number, program.race_date, program.surface) == (
        1,
        date(2026, 11, 21),
        "arena",
    )
    (entry,) = program.entries
    assert (entry.mandil, entry.weight, entry.jockey, entry.trainer) == (
        4,
        56,
        "A Jinete",
        "B Preparador",
    )
    assert entry.profile["recent_races"][0]["time"] == "0.52.88"
    assert entry.profile["recent_races"][0]["position"] == "1°/6"
    assert entry.profile["workouts"][0]["time"] == "0.23.2/5"


def test_empty_spa_rejects_missing_program() -> None:
    with pytest.raises(OfficialProgramError, match="reunión"):
        parse_program("<div id='root'></div>", URL)


def test_official_snapshot_ingestion_is_idempotent(
    migrated_engine: Engine,
    tmp_path: Path,
    program_html: str,
) -> None:
    store = LocalBlobStore(tmp_path / "blobs")
    source = [(URL, program_html, datetime(2026, 11, 19, tzinfo=UTC))]
    assert persist_programs(migrated_engine, store, source, date(2026, 11, 21)) == (1, 1)
    assert persist_programs(migrated_engine, store, source, date(2026, 11, 21)) == (0, 0)
    with migrated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(races)) == 1
        assert connection.scalar(select(func.count()).select_from(race_entries)) == 1
        snapshot = connection.execute(select(horse_stats_snapshots)).mappings().one()
        assert snapshot["source_url"] == URL
        assert snapshot["profile"]["workouts"][0]["time"] == "0.23.2/5"
