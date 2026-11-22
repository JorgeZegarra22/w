"""Match video-derived styles to a declared, pre-race field."""

import csv
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from io import StringIO

from benter_peru.entities.normalization import normalize_name
from benter_peru.ml.pace import PaceStyle

_STYLES = {
    "puntero": PaceStyle.PUNTERO,
    "puntero nato": PaceStyle.PUNTERO,
    "cerrador": PaceStyle.CERRADOR,
    "cerrador fuerte": PaceStyle.CERRADOR,
    "medio": PaceStyle.MEDIO,
    "intermedio": PaceStyle.MEDIO,
    "intermedio con remate": PaceStyle.MEDIO,
    "debutante": PaceStyle.MEDIO,
}
_REQUIRED = {
    "carrera",
    "mandil",
    "horse_name",
    "race_date",
    "last_race_date",
    "video_code",
    "style",
}


@dataclass(frozen=True, slots=True)
class VideoStyle:
    style: PaceStyle
    source_style: str
    previous_race_date: date | None
    video_code: str | None
    initial_position: str | None
    final_position: str | None

    @property
    def label(self) -> str:
        return (
            f"{self.style.value.capitalize()} · video" if self.video_code else "Medio · sin video"
        )


def load_video_styles(
    content: str, race_date: date, race_number: int, expected: Mapping[int, str]
) -> dict[int, VideoStyle]:
    reader = csv.DictReader(StringIO(content.removeprefix("\ufeff"), newline=""))
    if not _REQUIRED.issubset(reader.fieldnames or ()):
        raise ValueError("El CSV táctico no contiene las columnas requeridas.")
    styles = {}
    for row in reader:
        if (row.get("race_date") or "").strip() != race_date.isoformat():
            continue
        number = re.fullmatch(r"([1-9]\d*)[ªº°]?", (row.get("carrera") or "").strip())
        if not number or int(number[1]) != race_number:
            continue
        raw_mandil = (row.get("mandil") or "").strip()
        if not raw_mandil.isdecimal():
            raise ValueError("El CSV contiene mandiles inválidos para esta carrera.")
        mandil = int(raw_mandil)
        if mandil not in expected or mandil in styles:
            raise ValueError("El CSV contiene mandiles inesperados o repetidos para esta carrera.")
        if normalize_name(row.get("horse_name") or "") != normalize_name(expected[mandil]):
            raise ValueError(f"La identidad del caballo no coincide en el mandil {mandil}.")
        raw_style = (row.get("style") or "").strip()
        key = normalize_name(raw_style)
        if key not in _STYLES:
            raise ValueError(f"El estilo {raw_style!r} del mandil {mandil} no está reconocido.")
        code = (row.get("video_code") or "").strip() or None
        raw_date = (row.get("last_race_date") or "").strip()
        previous = date.fromisoformat(raw_date) if raw_date else None
        if previous is not None and previous >= race_date:
            raise ValueError(f"El video del mandil {mandil} debe ser anterior a la carrera.")
        if key != "debutante" and (previous is None or code is None):
            raise ValueError(
                f"Falta la fecha anterior o el identificador de video del mandil {mandil}."
            )
        styles[mandil] = VideoStyle(
            _STYLES[key],
            raw_style,
            previous,
            code,
            (row.get("initial_position") or "").strip() or None,
            (row.get("final_position") or "").strip() or None,
        )
    if styles and styles.keys() != expected.keys():
        raise ValueError("Faltan mandiles de la nómina en el CSV para esta carrera.")
    return styles
