"""In-memory prediction composition for the read-only dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from benter_peru.ml.features import FeatureEngine
from benter_peru.ml.models import BaselineRaceModel
from benter_peru.ui.queries import RaceOption, RaceParticipant

MODEL_WARNING = (
    "BASELINE SINTÉTICO NO CALIBRADO — production_ready=false. "
    "No se emiten recomendaciones de apuestas reales."
)


@dataclass(frozen=True, slots=True)
class PredictionRow:
    mandil: int
    horse_name: str
    win_probability: float
    top_three_probability: float


@dataclass(frozen=True, slots=True)
class DashboardPrediction:
    rows: tuple[PredictionRow, ...]
    warning: str


class PredictionService:
    """Calculate features and predictions without persisting model state or results."""

    def __init__(self, engine: Engine) -> None:
        self._feature_engine = FeatureEngine(engine)

    def for_race(
        self,
        race: RaceOption,
        participants: tuple[RaceParticipant, ...],
    ) -> DashboardPrediction:
        place_positions = min(3, len(participants))
        model = BaselineRaceModel(place_positions=place_positions).fit_synthetic()
        features = {
            participant.horse_id: self._feature_engine.for_horse(
                horse_id=participant.horse_id,
                race_date=race.scheduled_date,
                distance_meters=race.distance_meters,
                surface=race.surface,
            )
            for participant in participants
        }
        prediction = model.predict_race(features)
        rows = tuple(
            PredictionRow(
                mandil=participant.mandil,
                horse_name=participant.horse_name,
                win_probability=prediction.win_probabilities[participant.horse_id],
                top_three_probability=prediction.place_probabilities[
                    participant.horse_id
                ],
            )
            for participant in participants
        )
        return DashboardPrediction(rows=rows, warning=MODEL_WARNING)
