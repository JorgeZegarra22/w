from datetime import date

import pytest

from benter_peru.ml.pace import PaceStyle
from benter_peru.ml.video_pace import load_video_styles

DAY = date(2026, 11, 22)
HEADER = "carrera,mandil,horse_name,race_date,last_race_date,video_code,style\n"


def test_video_styles_match_race_name_and_club_number() -> None:
    source = HEADER + (
        "9ª,4,Otro,2026-11-22,2026-11-01,v1,Puntero\n"
        "10ª,4,Mr Peggy,2026-11-22,2026-10-18,v2,Cerrador Fuerte\n"
        "10ª,2,Otro,2026-11-22,2026-10-18,v2,Puntero Nato\n"
    )
    matched = load_video_styles(source, DAY, 10, {4: "Mr. Peggy", 2: "Otro"})
    assert matched[4].style == PaceStyle.CERRADOR
    assert matched[2].style == PaceStyle.PUNTERO
    assert matched[4].video_code == "v2"


@pytest.mark.parametrize(
    ("row", "error"),
    [
        ("10ª,4,Otro,2026-11-22,2026-10-18,v2,Cerrador", "identidad"),
        ("10ª,4,A,2026-11-22,2026-11-22,v2,Cerrador", "anterior"),
        ("10ª,3,A,2026-11-22,2026-10-18,v2,Cerrador", "mandiles"),
        ("10ª,4,A,2026-11-22,2026-10-18,v2,Dudoso", "estilo"),
    ],
)
def test_invalid_video_match_fails_closed(row: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        load_video_styles(HEADER + row, DAY, 10, {4: "A"})


def test_debutante_with_placeholder_date_and_positions_has_no_tactical_evidence() -> None:
    source = (
        HEADER.rstrip()
        + ",initial_position,final_position\n"
        + (
            "3ª,1,Debut,2026-11-22,2026-11-22,,Debutante,3,3\n"
            "3ª,2,Segundo,2026-11-22,2026-11-01,v2,Puntero,1,5\n"
        )
    )
    styles = load_video_styles(source, DAY, 3, {1: "Debut", 2: "Segundo"})
    assert styles[1].style == PaceStyle.MEDIO
    assert styles[1].label == "Debutante · sin video previo"
    assert styles[1].previous_race_date is None
    assert styles[1].initial_position is None and styles[1].final_position is None
    assert styles[2].style == PaceStyle.PUNTERO
