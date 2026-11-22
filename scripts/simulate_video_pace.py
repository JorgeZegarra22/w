"""Simulate pace and final-stretch biomechanics from traceable prior videos."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

from benter_peru.ml.artifacts import EnsembleArtifactConfig
from benter_peru.ml.models import EnsembleRaceModel
from benter_peru.ml.simulator import (
    COLLISION_LEADERS,
    FINAL_STRETCH_ENERGY,
    FINAL_STRETCH_METERS,
    MAX_STRIDE_MODULATION,
    PaceParticipant,
    count_leaders,
    simulate_race,
)
from benter_peru.ml.video_pace import load_video_styles
from benter_peru.ui.queries import DashboardRepository, RaceOption
from benter_peru.ui.service import PredictionService

SIMULATIONS = 10_000
SEED = 42


def simulate_official_race(
    repository: DashboardRepository, service: PredictionService, race: RaceOption, content: str
) -> dict[str, object]:
    entrants = repository.participants_for_race(race.id)
    try:
        styles = load_video_styles(
            content,
            race.scheduled_date,
            race.race_number,
            {e.mandil: e.horse_name for e in entrants},
        )
    except ValueError as exc:
        raise ValueError(f"Carrera {race.race_number}: {exc}") from exc
    if not styles:
        raise ValueError(f"Carrera {race.race_number}: el CSV no contiene estilos")
    prediction = service.for_race(race, entrants)

    participants = [
        PaceParticipant(
            r.participant_id,
            r.win_probability,
            assessment.style,
            assessment.fatigue_factor,
            assessment.stride_drop_pct,
        )
        for r in prediction.rows
        for assessment in (styles[r.mandil],)
    ]
    pace = simulate_race(participants, SIMULATIONS, seed=SEED, include_biomechanics=False)
    adjusted = simulate_race(participants, SIMULATIONS, seed=SEED)
    leaders = count_leaders(participants)
    runners = [
        {
            "mandil": r.mandil,
            "horse": r.horse_name,
            "source_style": assessment.source_style,
            "simulator_style": assessment.style.value,
            "video_code": assessment.video_code,
            "previous_race_date": (
                assessment.previous_race_date.isoformat() if assessment.previous_race_date else None
            ),
            "initial_position": assessment.initial_position,
            "final_position": assessment.final_position,
            "stride_frequency": assessment.stride_frequency,
            "fatigue_factor": assessment.fatigue_factor,
            "stride_drop_pct": assessment.stride_drop_pct,
            "ensemble_probability": r.win_probability,
            "pace_probability": pace[r.participant_id],
            "biomechanics_probability": adjusted[r.participant_id],
            "biomechanics_delta_percentage_points": 100
            * (adjusted[r.participant_id] - pace[r.participant_id]),
            "delta_percentage_points": 100 * (adjusted[r.participant_id] - r.win_probability),
        }
        for r in prediction.rows
        for assessment in (styles[r.mandil],)
    ]
    most_helped = max(
        prediction.rows,
        key=lambda row: (adjusted[row.participant_id] - pace[row.participant_id], -row.mandil),
    )
    beneficiary = None
    if adjusted[most_helped.participant_id] > pace[most_helped.participant_id]:
        beneficiary = next(row for row in runners if row["mandil"] == most_helped.mandil)
    return {
        "race": race.race_number,
        "race_date": race.scheduled_date.isoformat(),
        "leaders": leaders,
        "pace_collision": leaders >= COLLISION_LEADERS,
        "original_probability_sum": sum(r.win_probability for r in prediction.rows),
        "pace_probability_sum": sum(pace.values()),
        "adjusted_probability_sum": sum(adjusted.values()),
        "most_helped": beneficiary,
        "runners": runners,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--styles", type=Path, required=True)
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--race", type=int, help="omit to simulate the entire meeting")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("el archivo de salida debe ser nuevo")

    payload = args.styles.read_bytes()
    content = payload.decode("utf-8-sig")
    repository = DashboardRepository.open(args.database)
    try:
        races = [
            race
            for race in repository.races_for_meeting(args.meeting)
            if args.race is None or race.race_number == args.race
        ]
        if not races:
            parser.error("la reunión o carrera no existe en la base")
        config = EnsembleArtifactConfig.from_env()
        model = EnsembleRaceModel.load(
            model_path=config.model_path,
            dataset_path=config.dataset_path,
            expected_sha256=config.expected_sha256,
        )
        service = PredictionService(model)
        race_reports = [
            simulate_official_race(repository, service, race, content) for race in races
        ]
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        repository.close()

    report = {
        "meeting": args.meeting,
        "source": args.styles.name,
        "source_sha256": sha256(payload).hexdigest(),
        "model_sha256": model.metadata.artifact_sha256,
        "simulations_requested": SIMULATIONS,
        "seed": SEED,
        "collision_threshold": COLLISION_LEADERS,
        "biomechanics": {
            "calibrated": False,
            "final_stretch_meters": FINAL_STRETCH_METERS,
            "log_strength_by_fatigue_factor": FINAL_STRETCH_ENERGY,
            "max_stride_drop_modulation": MAX_STRIDE_MODULATION,
        },
    }
    report.update({"races": race_reports} if args.race is None else race_reports[0])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
