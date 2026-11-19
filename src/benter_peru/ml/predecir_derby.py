"""Compatibility CLI for predicting any registered meeting race."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benter_peru.ml.artifacts import RealModelArtifactConfig
from benter_peru.ml.models import RealLightGBMRaceModel
from benter_peru.ui.queries import DashboardRepository
from benter_peru.ui.service import PredictionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m benter_peru.ml.predecir_derby")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--race", type=int, required=True)
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    repository = DashboardRepository.open(arguments.database)
    try:
        races = repository.races_for_meeting(arguments.meeting)
        selected = next(
            (race for race in races if race.race_number == arguments.race), None
        )
        if selected is None:
            raise SystemExit("meeting/race not found")
        config = RealModelArtifactConfig.from_env()
        model = RealLightGBMRaceModel.load(
            model_path=config.model_path,
            dataset_path=config.dataset_path,
            expected_sha256=config.expected_sha256,
        )
        result = PredictionService(model).for_race(
            selected, repository.participants_for_race(selected.id)
        )
        print(
            json.dumps(
                {
                    "meeting": selected.meeting_code,
                    "race": selected.race_number,
                    "distance_meters": selected.distance_meters,
                    "surface": selected.surface,
                    "provenance": result.provenance,
                    "participants": [
                        {
                            "mandil": row.mandil,
                            "horse": row.horse_name,
                            "win_probability": row.win_probability,
                            "top_three_probability": row.top_three_probability,
                            "fair_odds": row.fair_odds,
                        }
                        for row in result.rows
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
