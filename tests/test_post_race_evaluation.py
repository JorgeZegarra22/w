from datetime import date

import pytest

from scripts.evaluate_results import score_race, summarize
from scripts.scrape_results import parse_wagico

DAY = date(2026, 11, 21)


def _result() -> bytes:
    return """<html>
    <script type="application/ld+json">{"@type":"SportsEvent","eventStatus":
    "https://schema.org/EventCompleted","startDate":"2026-11-21T16:50:00-03:00",
    "location":{"name":"Hipódromo de Monterrico"}}</script>
    <main><h1>Carrera 4 · Handicap</h1><p>Tiempo: 0.59.80</p>
    <section><h2>Llegada</h2><ol>
    <li><span>1°</span><span aria-label="N° 8">8</span>
        <span><span><span>Uno</span></span></span></li>
    <li><span>U°</span><span aria-label="N° 4">4</span>
        <span><span><span>Dos</span></span></span></li>
    <li><span>Retirado</span><span aria-label="N° 3">3</span>
        <span><span><span>Tres</span></span></span></li>
    </ol></section></main></html>""".encode()


def test_parse_keeps_last_place_and_scratch_separate() -> None:
    result = parse_wagico(_result(), DAY, 4)
    assert result.winner_time == "0.59.80"
    assert [(r.mandil, r.name, r.position, r.display_position) for r in result.runners] == [
        (8, "Uno", 1, "1°"),
        (4, "Dos", 2, "U°"),
        (3, "Tres", None, "Retirado"),
    ]


def test_pre_race_scoring_keeps_declared_field_and_reports_scratch() -> None:
    result = parse_wagico(_result(), DAY, 4)
    scored = score_race(result, {3: ("Tres", 0.5), 8: ("Uno", 0.3), 4: ("Dos", 0.2)})
    assert not scored.hit and scored.favorite_position is None
    assert scored.brier == pytest.approx(0.78)
    assert scored.log_loss == pytest.approx(1.2039728043)
    assert summarize([scored])["favorites_with_position"] == 0


def test_rejects_mismatched_horse_identity() -> None:
    with pytest.raises(ValueError, match="identidad"):
        score_race(
            parse_wagico(_result(), DAY, 4), {3: ("Tres", 0.5), 8: ("Otro", 0.3), 4: ("Dos", 0.2)}
        )
