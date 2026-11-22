"""Run the existing pace simulation with traceable historical video styles."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

from benter_peru.ml.artifacts import EnsembleArtifactConfig
from benter_peru.ml.models import EnsembleRaceModel
from benter_peru.ml.simulator import (
    COLLISION_LEADERS,
    PaceParticipant,
    count_leaders,
    simulate_race,
)
from benter_peru.ml.video_pace import load_video_styles
from benter_peru.ui.queries import DashboardRepository
from benter_peru.ui.service import PredictionService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--styles", type=Path, required=True)
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--race", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("el archivo de salida debe ser nuevo")

    payload = args.styles.read_bytes()
    repository = DashboardRepository.open(args.database)
    try:
        race = next(
            (r for r in repository.races_for_meeting(args.meeting) if r.race_number == args.race),
            None,
        )
        if race is None:
            parser.error("la reunión o carrera no existe en la base")
        entrants = repository.participants_for_race(race.id)
        styles = load_video_styles(
            payload.decode("utf-8-sig"),
            race.scheduled_date,
            race.race_number,
            {e.mandil: e.horse_name for e in entrants},
        )
        if not styles:
            parser.error("el CSV no contiene estilos para la carrera seleccionada")
        config = EnsembleArtifactConfig.from_env()
        model = EnsembleRaceModel.load(
            model_path=config.model_path,
            dataset_path=config.dataset_path,
            expected_sha256=config.expected_sha256,
        )
        prediction = PredictionService(model).for_race(race, entrants)
    finally:
        repository.close()

    participants = [
        PaceParticipant(r.participant_id, r.win_probability, styles[r.mandil].style)
        for r in prediction.rows
    ]
    simulations, seed = 10_000, 42
    adjusted = simulate_race(participants, simulations, seed=seed)
    report = {
        "meeting": args.meeting,
        "race": args.race,
        "race_date": race.scheduled_date.isoformat(),
        "source": args.styles.name,
        "source_sha256": sha256(payload).hexdigest(),
        "model_sha256": model.metadata.artifact_sha256,
        "simulations_requested": simulations,
        "seed": seed,
        "leaders": count_leaders(participants),
        "collision_threshold": COLLISION_LEADERS,
        "pace_collision": count_leaders(participants) >= COLLISION_LEADERS,
        "original_probability_sum": sum(r.win_probability for r in prediction.rows),
        "adjusted_probability_sum": sum(adjusted.values()),
        "runners": [
            {
                "mandil": r.mandil,
                "horse": r.horse_name,
                "source_style": assessment.source_style,
                "simulator_style": assessment.style.value,
                "video_code": assessment.video_code,
                "previous_race_date": (
                    assessment.previous_race_date.isoformat()
                    if assessment.previous_race_date
                    else None
                ),
                "initial_position": assessment.initial_position,
                "final_position": assessment.final_position,
                "ensemble_probability": r.win_probability,
                "pace_probability": adjusted[r.participant_id],
                "delta_percentage_points": 100 * (adjusted[r.participant_id] - r.win_probability),
            }
            for r in prediction.rows
            for assessment in (styles[r.mandil],)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
