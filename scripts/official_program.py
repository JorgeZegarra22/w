"""Collect and materialize the official Monterrico race programs for one date."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from benter_peru.db.engine import create_database_engine
from benter_peru.db.migrations import upgrade_database
from benter_peru.scrapers.official_browser import official_page, render_program
from benter_peru.scrapers.official_scraper import (
    BASE_URL,
    MEETING_URL,
    OfficialProgramError,
    discover_race_urls,
    parse_program,
)
from benter_peru.scrapers.official_store import Capture, persist_programs
from benter_peru.storage.local import LocalBlobStore


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--blobs", required=True, type=Path)
    parser.add_argument("--captures", type=Path, help="read and save local HTML captures")
    parser.add_argument("--seed-race", type=int, help="official race ID if no meeting is listed")
    parser.add_argument("--channel", help="installed Playwright channel, e.g. msedge")
    parser.add_argument("--expected-races", type=int)
    args = parser.parse_args(argv)
    if args.seed_race is not None and args.seed_race <= 0:
        parser.error("--seed-race debe ser positivo")
    agent = os.environ.get("BENTER_USER_AGENT", "").strip()
    if not agent:
        parser.error("define BENTER_USER_AGENT con un identificador y contacto válidos")

    captures: list[Capture] = []
    with official_page(agent, channel=args.channel) as page:

        def collect(label: str, url: str, *, meeting: bool = False) -> Capture:
            path = args.captures / f"official-contract-{label}.html" if args.captures else None
            if path is not None and path.is_file():
                return (
                    url,
                    path.read_bytes().decode("utf-8"),
                    datetime.fromtimestamp(
                        path.stat().st_mtime,
                        UTC,
                    ),
                )
            html = render_program(page, url, meeting=meeting)
            fetched = datetime.now(UTC)
            if not meeting:
                parse_program(html, url)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    output.write(html.encode("utf-8"))
            return url, html, fetched

        _, index, _ = collect("reunion", MEETING_URL, meeting=True)
        urls = discover_race_urls(index)
        if not urls and args.seed_race is not None:
            seed = f"{BASE_URL}/programa?carrera={args.seed_race}"
            capture = collect(str(args.seed_race), seed)
            urls = tuple(dict.fromkeys((seed, *discover_race_urls(capture[1]))))
            captures.append(capture)
        if not urls:
            raise OfficialProgramError("reunión sin enlaces; indica --seed-race si conoces un ID")
        for url in urls:
            if not captures or url != captures[0][0]:
                captures.append(collect(url.rsplit("=", 1)[1], url))

    selected = [
        capture
        for capture in captures
        if parse_program(capture[1], capture[0]).race_date == args.date
    ]
    if args.expected_races is not None and len(selected) != args.expected_races:
        raise OfficialProgramError(
            f"se esperaban {args.expected_races} carreras, se encontraron {len(selected)}"
        )
    args.database.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(f"sqlite+pysqlite:///{args.database.resolve().as_posix()}")
    try:
        upgrade_database(engine)
        races, snapshots = persist_programs(engine, LocalBlobStore(args.blobs), selected, args.date)
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "discovered": len(urls),
                "selected": len(selected),
                "races_created": races,
                "snapshots_created": snapshots,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
