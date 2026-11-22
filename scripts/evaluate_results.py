"""Reconstruct pre-race forecasts and score a secondary result capture."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path
from statistics import mean
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from benter_peru.entities.normalization import normalize_name
from benter_peru.ml.artifacts import EnsembleArtifactConfig
from benter_peru.ml.models import EnsembleRaceModel
from benter_peru.ui.queries import DashboardRepository
from benter_peru.ui.service import PredictionService
from scripts.scrape_results import RaceResult, Runner, result_url


@dataclass(frozen=True, slots=True)
class RaceScore:
    race: int
    favorite: str
    favorite_probability: float
    favorite_position: int | None
    winner: str
    winner_probability: float
    hit: bool
    brier: float
    log_loss: float
    field_size: int
    source_url: str


def score_race(result: RaceResult, predictions: dict[int, tuple[str, float]]) -> RaceScore:
    observed = {row.mandil: row for row in result.runners}
    if observed.keys() != predictions.keys():
        raise ValueError(f"Carrera {result.number}: la nómina de mandiles no coincide")
    for mandil, (name, p) in predictions.items():
        if normalize_name(name) != normalize_name(observed[mandil].name):
            raise ValueError(f"Carrera {result.number}, mandil {mandil}: identidad no coincide")
        if not math.isfinite(p) or not 0 < p <= 1:
            raise ValueError(f"Carrera {result.number}: probabilidad inválida")
    if not math.isclose(math.fsum(p for _, p in predictions.values()), 1.0, abs_tol=1e-9):
        raise ValueError(f"Carrera {result.number}: las probabilidades no suman 1")
    winners = [r for r in result.runners if r.position == 1]
    if len(winners) != 1:
        raise ValueError(f"Carrera {result.number}: no hay un único ganador")
    winner = winners[0]
    favorite_mandil = min(predictions, key=lambda m: (-predictions[m][1], m))
    favorite, favorite_probability = predictions[favorite_mandil]
    favorite_position = observed[favorite_mandil].position
    return RaceScore(
        result.number,
        favorite,
        favorite_probability,
        favorite_position,
        winner.name,
        predictions[winner.mandil][1],
        favorite_mandil == winner.mandil,
        math.fsum((p - (mandil == winner.mandil)) ** 2 for mandil, (_, p) in predictions.items()),
        -math.log(predictions[winner.mandil][1]),
        len(predictions),
        result.source_url,
    )


def summarize(scores: list[RaceScore]) -> dict[str, float | int | None]:
    if not scores:
        raise ValueError("No hay carreras evaluadas")
    positions = [row.favorite_position for row in scores if row.favorite_position is not None]
    return {
        "races": len(scores),
        "hits": sum(row.hit for row in scores),
        "top1": mean(row.hit for row in scores),
        "brier": mean(row.brier for row in scores),
        "log_loss": mean(row.log_loss for row in scores),
        "favorite_mean_position": mean(positions) if positions else None,
        "favorites_with_position": len(positions),
        "uniform_top1_expected": mean(1 / row.field_size for row in scores),
        "uniform_brier": mean(1 - 1 / row.field_size for row in scores),
        "uniform_log_loss": mean(math.log(row.field_size) for row in scores),
    }


def _read_results(path: Path, day: date) -> dict[int, RaceResult]:
    capture = json.loads(path.read_text(encoding="utf-8"))
    if capture.get("source") != "WAGICO" or capture.get("source_status") != "secondary_diagnostic":
        raise ValueError("La procedencia del archivo debe ser WAGICO como fuente secundaria")
    by_number = {}
    for row in capture["races"]:
        values = dict(row)
        values["runners"] = tuple(Runner(**runner) for runner in row["runners"])
        result = RaceResult(**values)
        if (
            result.number in by_number
            or result.race_date != day.isoformat()
            or result.source_url != result_url(day, result.number)
        ):
            raise ValueError("Captura con carreras duplicadas, URLs inesperadas o fecha incorrecta")
        by_number[result.number] = result
    return by_number


def evaluate(
    database: Path,
    config: EnsembleArtifactConfig,
    day: date,
    meeting: str,
    results: dict[int, RaceResult],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    model = EnsembleRaceModel.load(
        model_path=config.model_path,
        dataset_path=config.dataset_path,
        expected_sha256=config.expected_sha256,
    )
    service = PredictionService(model)
    db = DashboardRepository.open(database)
    scores = []
    additions = []
    captured_before = ZoneInfo("America/Lima")
    try:
        races = [race for race in db.races_for_meeting(meeting) if race.scheduled_date == day]
        if {race.race_number for race in races} != results.keys():
            raise ValueError("La cobertura de la fuente no coincide con las carreras programadas")
        for race in races:
            runners = db.participants_for_race(race.id)
            snapshots = db.horse_snapshots_for_race(race.id)
            if any(r.mandil not in snapshots for r in runners) or any(
                snapshot.fetched_at.replace(tzinfo=snapshot.fetched_at.tzinfo or UTC)
                .astimezone(captured_before)
                .date()
                >= day
                for snapshot in snapshots.values()
            ):
                raise ValueError(
                    f"Carrera {race.race_number}: no se verificó la nómina anterior al día"
                )
            prediction = service.for_race(race, runners)
            result = results[race.race_number]
            scores.append(
                score_race(
                    result,
                    {row.mandil: (row.horse_name, row.win_probability) for row in prediction.rows},
                )
            )
            lookup = {row.mandil: row for row in result.runners}
            start = datetime.fromisoformat(result.started_at).astimezone(captured_before)
            for entrant in runners:
                outcome = lookup[entrant.mandil]
                if outcome.position is None:
                    continue  # Do not turn a withdrawal into a training defeat.
                program = urlsplit(snapshots[entrant.mandil].source_url)
                additions.append(
                    {
                        "Fecha": day.isoformat(),
                        "Carrera": race.race_number,
                        "Reunion": meeting.rsplit("-", 1)[-1],
                        "Hipodromo": "Monterrico",
                        "Numero_Mandil": entrant.mandil,
                        "Caballo": outcome.name,
                        "Posicion": outcome.position,
                        "Tiempo_Ganador": result.winner_time or "",
                        "Hora": start.strftime("%H:%M"),
                        "Distancia": race.distance_meters,
                        "Peso": f"{entrant.weight:g}k",
                        "Peso_Kg": entrant.weight,
                        "Jinete": entrant.jockey_name,
                        "Preparador": entrant.trainer_name,
                        "Stud": entrant.stud_name,
                        "Id_Carrera": parse_qs(program.query).get("carrera", [""])[0],
                        "Resultado_Posicion_Publicada": outcome.display_position,
                        "Resultado_Fuente": "WAGICO (secundaria)",
                        "Resultado_URL": result.source_url,
                        "Resultado_SHA256": result.content_sha256,
                        "Resultado_Capturado_UTC": result.fetched_at,
                        "Uso": "diagnostico_provisional",
                    }
                )
    finally:
        db.close()
    return {
        "source": "WAGICO",
        "source_status": "secondary_diagnostic",
        "meeting": meeting,
        "date": day.isoformat(),
        "field_policy": "declared_entries_in_pre_race_program",
        "model_sha256": model.metadata.artifact_sha256,
        "metrics": summarize(scores),
        "races": [asdict(item) for item in scores],
    }, additions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = EnsembleArtifactConfig.from_env()
    raw = config.dataset_path.read_bytes()
    dataset = csv.DictReader(StringIO(raw.decode("utf-8-sig"), newline=""))
    historical = list(dataset)
    dates = [date.fromisoformat(row["Fecha"]) for row in historical]
    if not dates or max(dates) >= args.date:
        raise ValueError("El dataset debe contener exclusivamente fechas anteriores a la jornada")
    csv_path = args.output_dir / f"resultados_wagico_{args.date}_enriquecido.csv"
    json_path = args.output_dir / f"diagnostico_wagico_{args.date}.json"
    if csv_path.exists() or json_path.exists():
        parser.error("los archivos de salida ya existen; usa otra carpeta")
    report, additions = evaluate(
        args.database, config, args.date, args.meeting, _read_results(args.results, args.date)
    )
    report.update(
        dataset_sha256=sha256(raw).hexdigest(),
        historical_rows=len(historical),
        historical_last_date=max(dates).isoformat(),
        added_rows=len(additions),
    )
    fields = list(
        dict.fromkeys([*(dataset.fieldnames or []), *(key for row in additions for key in row)])
    )
    if sha256(config.dataset_path.read_bytes()).hexdigest() != report["dataset_sha256"]:
        raise ValueError("El dataset histórico cambió durante la evaluación")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with csv_path.open("x", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(historical)
        writer.writerows(additions)
    with json_path.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
