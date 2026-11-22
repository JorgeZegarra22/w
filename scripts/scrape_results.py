"""Collect completed Monterrico results from WAGICO as secondary evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from lxml.html import HtmlElement, fromstring  # type: ignore[import-untyped]

from benter_peru.http.client import HttpClientConfig, ResponsibleHttpClient
from benter_peru.policy import PolicyGate


@dataclass(frozen=True, slots=True)
class Runner:
    mandil: int
    name: str
    position: int | None
    display_position: str


@dataclass(frozen=True, slots=True)
class RaceResult:
    number: int
    race_date: str
    started_at: str
    winner_time: str | None
    runners: tuple[Runner, ...]
    source_url: str
    content_sha256: str
    fetched_at: str


def _text(node: HtmlElement) -> str:
    return " ".join(node.text_content().split())


def parse_wagico(content: bytes, day: date, number: int) -> RaceResult:
    root = fromstring(content.decode("utf-8"))
    events = [
        json.loads(str(raw)) for raw in root.xpath("//script[@type='application/ld+json']/text()")
    ]
    event = next(
        (e for e in events if isinstance(e, dict) and e.get("@type") == "SportsEvent"), None
    )
    if event is None or event.get("eventStatus") != "https://schema.org/EventCompleted":
        raise ValueError(f"Carrera {number}: el resultado aún no figura como finalizado")
    start = datetime.fromisoformat(event["startDate"])
    if start.utcoffset() is None or start.astimezone(ZoneInfo("America/Lima")).date() != day:
        raise ValueError(f"Carrera {number}: la fecha publicada difiere de la solicitada")
    if "Monterrico" not in event.get("location", {}).get("name", "") or not any(
        re.match(rf"^Carrera\s+{number}\b", _text(node)) for node in root.xpath("//h1")
    ):
        raise ValueError(f"Carrera {number}: hipódromo o número de carrera no coincide")

    races = root.xpath("//section[h2[normalize-space()='Llegada']]/ol/li")
    if not races:
        raise ValueError(f"Carrera {number}: no se encontró una llegada")
    extracted = []
    for row in races:
        cells = row.xpath("./span")
        names = cells[2].xpath("./span[1]/span[1]") if len(cells) >= 3 else []
        if not names or not _text(names[0]) or not _text(cells[1]).isdigit():
            raise ValueError(f"Carrera {number}: fila de llegada incompleta")
        extracted.append((int(_text(cells[1])), _text(names[0]), _text(cells[0])))
    if len({m for m, _, _ in extracted}) != len(extracted):
        raise ValueError(f"Carrera {number}: mandiles duplicados")
    classified = sum(bool(re.fullmatch(r"(?:[1-9]\d*|U)[°ºª]", label)) for _, _, label in extracted)
    runners = []
    for mandil, name, label in extracted:
        match = re.fullmatch(r"([1-9]\d*)[°ºª]", label)
        position = int(match[1]) if match else None
        if label in {"U°", "Uº"}:
            position = classified
        elif position is None and label.casefold() not in {"retirado", "no llegó", "descalificado"}:
            raise ValueError(f"Carrera {number}: posición no reconocida {label!r}")
        runners.append(Runner(mandil, name, position, label))
    if sum(row.position == 1 for row in runners) != 1:
        raise ValueError(f"Carrera {number}: se requiere un único ganador identificado")
    visible = " ".join(str(s) for s in root.xpath("//body//text()[not(ancestor::script)]"))
    if not visible:
        visible = " ".join(str(s) for s in root.xpath("//main//text()"))
    clock = re.search(r"\bTiempo\s*:\s*([0-9]+(?:[.:][0-9]+)+)", visible)
    return RaceResult(
        number,
        day.isoformat(),
        start.isoformat(),
        clock[1] if clock else None,
        tuple(runners),
        result_url(day, number),
        sha256(content).hexdigest(),
        datetime.now(UTC).isoformat(),
    )


def result_url(day: date, number: int) -> str:
    return f"https://wagico.com/resultados/mont/{day.isoformat()}/{number}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--races", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.races < 1 or args.output.exists():
        parser.error("indica un total positivo y un archivo de salida nuevo")
    agent = os.environ.get("BENTER_USER_AGENT", "").strip()
    if not agent:
        parser.error("define BENTER_USER_AGENT antes de ejecutar el scraper")
    results = []
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as transport:
        client = ResponsibleHttpClient(HttpClientConfig(user_agent=agent), client=transport)
        policy = PolicyGate(client)
        for number in range(1, args.races + 1):
            url = result_url(args.date, number)
            if not policy.evaluate(url).allowed:
                raise RuntimeError(f"La política de WAGICO denegó {url}")
            response = client.fetch(url)
            response.raise_for_status()
            results.append(parse_wagico(response.content, args.date, number))
            print(f"Carrera {number}: {len(results[-1].runners)} filas", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(
            {
                "source": "WAGICO",
                "source_status": "secondary_diagnostic",
                "races": [asdict(item) for item in results],
            },
            output,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
