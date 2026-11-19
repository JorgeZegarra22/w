"""Parse Monterrico's public race cards and discover official program links."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TypedDict
from urllib.parse import parse_qs, urljoin, urlsplit

from lxml.html import HtmlElement, fromstring  # type: ignore[import-untyped]

OFFICIAL_HOST = "hipodromodemonterrico.com.pe"
BASE_URL = f"https://{OFFICIAL_HOST}/monterrico"
MEETING_URL = f"{BASE_URL}/reunion"
PROGRAM_PATH = "/monterrico/programa"
_MEETING = re.compile(r"Reunión\s+(\d+)\s*,.*?(\d{4}-\d{2}-\d{2})")
_DATE = re.compile(r"\d{1,2}[A-Za-z]{3}\d{2}")


class OfficialProgramError(ValueError):
    """The page does not contain an unambiguous race program."""


class HorseProfile(TypedDict):
    general: list[dict[str, str]]
    by_track: list[dict[str, str]]
    recent_races: list[dict[str, str]]
    workouts: list[dict[str, str | int]]


@dataclass(frozen=True, slots=True)
class OfficialEntry:
    mandil: int
    horse_name: str
    weight: Decimal
    jockey: str
    trainer: str
    stud: str
    profile: HorseProfile


@dataclass(frozen=True, slots=True)
class OfficialProgram:
    url: str
    official_meeting: str
    race_date: date
    race_number: int
    distance_meters: int
    surface: str
    scheduled_time: str
    entries: tuple[OfficialEntry, ...]


def _text(node: HtmlElement) -> str:
    return " ".join(node.text_content().split())


def discover_race_urls(html: str) -> tuple[str, ...]:
    urls: dict[str, None] = {}
    for href in fromstring(html or "<html/>").xpath("//a/@href"):
        parsed = urlsplit(urljoin(MEETING_URL, href))
        ids = parse_qs(parsed.query).get("carrera", [])
        if (
            parsed.scheme == "https"
            and parsed.netloc == OFFICIAL_HOST
            and parsed.path == PROGRAM_PATH
            and len(ids) == 1
            and re.fullmatch(r"[0-9]+", ids[0])
        ):
            urls[f"{BASE_URL}/programa?carrera={ids[0]}"] = None
    return tuple(urls)


def parse_program(html: str, url: str) -> OfficialProgram:
    root = fromstring(html or "<html/>")
    headings = root.xpath("//p[contains(., 'Reunión')]")
    for heading in headings:
        match = _MEETING.search(_text(heading))
        if match:
            break
    else:
        raise OfficialProgramError("encabezado de reunión no disponible")
    header = heading.getparent().getnext()
    header_text = " ".join(str(value).strip() for value in header.itertext())
    number = re.search(r"\b(\d{1,2})[ªº°]", header_text)
    distance = re.search(r"\b([0-9.,]+)\s*m\b", header_text)
    time = re.search(r"\b(\d{1,2}:\d{2})\s*hrs", header_text)
    track = re.search(r"\b(arena|c[ée]sped|pasto)\b", header_text, re.I)
    if not (number and distance and time and track):
        raise OfficialProgramError("contexto incompleto de la carrera")
    cards = root.xpath("//div[contains(@class, 'border-2 rounded-lg overflow-hidden')]")
    entries = tuple(_entry(card) for card in cards)
    if not entries or len({item.mandil for item in entries}) != len(entries):
        raise OfficialProgramError("nómina ausente o con mandiles duplicados")
    return OfficialProgram(
        url,
        match[1],
        date.fromisoformat(match[2]),
        int(number[1]),
        int(re.sub(r"[.,]", "", distance[1])),
        "arena" if track[1].lower() == "arena" else "cesped",
        time[1],
        entries,
    )


def _entry(card: HtmlElement) -> OfficialEntry:
    mandils = card.xpath("./div[1]/div[1]/span[1]")
    names = card.xpath("./div[1]//a[normalize-space(.) != '']")
    weights = [
        value
        for node in card.xpath("./div[1]//span[not(*)]")
        if (value := re.fullmatch(r"(\d{2}(?:[.,]\d+)?)\s*k(?:g)?", _text(node)))
    ]
    jockey = _labeled_person(card, "Jinete")
    trainer = _labeled_person(card, "Preparador")
    studs = card.xpath("./div[1]//div[text()[contains(., ' Stud ')]]")
    stud = _text(studs[0]).partition(" Stud ")[2] if studs else ""
    if not (mandils and names and weights and jockey and trainer and stud):
        raise OfficialProgramError("datos incompletos de un participante")
    profile: HorseProfile = {"general": [], "by_track": [], "recent_races": [], "workouts": []}
    fields = ("scope", "starts", "wins", "second", "third", "fourth", "nt", "earnings")
    for row in _table_rows(card, "./div[1]//table/tbody/tr"):
        if len(row) == len(fields):
            target = "general" if row[0].isdigit() or row[0] == "Total" else "by_track"
            stats = dict(zip(fields, row, strict=True))
            if target == "general":
                profile["general"].append(stats)
            else:
                profile["by_track"].append(stats)
    for row in _table_rows(card, "./div[position()>1]//table/tbody/tr"):
        if len(row) >= 14 and _DATE.fullmatch(row[0]):
            profile["recent_races"].append(
                {
                    "date": row[0],
                    "track": row[1],
                    "distance": row[2],
                    "time": row[3],
                    "position": row[6],
                    "comments": row[13],
                }
            )
    profile["recent_races"] = profile["recent_races"][:5]
    for row in card.xpath(".//span[normalize-space(text())='Aprontes']/following-sibling::span"):
        text = _text(row)
        workout = re.match(r"(\d{1,2}[A-Za-z]{3}\d{2})\s+(\S+)\s+(\d+)m\b", text)
        clocks = row.xpath("./span[contains(@class, 'font-mono')]")
        if workout and clocks:
            profile["workouts"].append(
                {
                    "date": workout[1],
                    "track": workout[2],
                    "distance_meters": int(workout[3]),
                    "time": _text(clocks[0]),
                }
            )
    return OfficialEntry(
        int(_text(mandils[0])),
        _text(names[0]),
        Decimal(weights[0][1].replace(",", ".")),
        jockey,
        trainer,
        stud,
        profile,
    )


def _labeled_person(card: HtmlElement, label: str) -> str:
    labels = card.xpath("./div[1]//span[normalize-space(text())=$label]", label=label)
    return " ".join((labels[0].tail or "").split()) if labels else ""


def _table_rows(card: HtmlElement, selector: str) -> list[list[str]]:
    return [[_text(cell) for cell in row.xpath("./td")] for row in card.xpath(selector)]
