"""In-memory prediction composition for the read-only dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from benter_peru.ml.models import RealRacePrediction
from benter_peru.ml.real_features import RealRaceParticipant
from benter_peru.ui.queries import RaceOption, RaceParticipant


class RacePredictor(Protocol):
    def predict_race(
        self,
        *,
        race_date: date,
        distance_meters: int,
        surface: str,
        participants: tuple[RealRaceParticipant, ...],
    ) -> RealRacePrediction: ...


@dataclass(frozen=True, slots=True)
class PredictionRow:
    mandil: int
    horse_name: str
    win_probability: float
    top_three_probability: float
    fair_odds: float


@dataclass(frozen=True, slots=True)
class DashboardPrediction:
    rows: tuple[PredictionRow, ...]
    provenance: str
    training_rows: int


class PredictionService:
    """Calculate features and predictions without persisting model state or results."""

    def __init__(self, predictor: RacePredictor) -> None:
        self._predictor = predictor

    def for_race(
        self,
        race: RaceOption,
        participants: tuple[RaceParticipant, ...],
    ) -> DashboardPrediction:
        model_participants = tuple(
            RealRaceParticipant(
                participant_id=participant.horse_id,
                horse_name=participant.horse_name,
                jockey_name=participant.jockey_name,
                trainer_name=participant.trainer_name,
                stud_name=participant.stud_name,
                weight=participant.weight,
                mandil=participant.mandil,
            )
            for participant in participants
        )
        prediction = self._predictor.predict_race(
            race_date=race.scheduled_date,
            distance_meters=race.distance_meters,
            surface=race.surface,
            participants=model_participants,
        )
        rows = tuple(
            PredictionRow(
                mandil=participant.mandil,
                horse_name=participant.horse_name,
                win_probability=prediction.win_probabilities[participant.horse_id],
                top_three_probability=prediction.place_probabilities[
                    participant.horse_id
                ],
                fair_odds=prediction.fair_odds[participant.horse_id],
            )
            for participant in participants
        )
        training_rows = prediction.metadata.training_rows
        provenance = (
            "Predicción generada por el modelo LightGBM entrenado con "
            f"{training_rows:,} registros históricos "
            f"({prediction.metadata.training_start.year}-"
            f"{prediction.metadata.training_end.year})"
        )
        return DashboardPrediction(
            rows=rows,
            provenance=provenance,
            training_rows=training_rows,
        )
