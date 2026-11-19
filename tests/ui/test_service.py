"""Real-model dashboard prediction composition tests."""

from datetime import date
from pathlib import Path

from benter_peru.ml.models import RealModelMetadata, RealRacePrediction
from benter_peru.ui.queries import DashboardRepository, RaceOption
from benter_peru.ui.service import PredictionService

from .test_queries import _create_dashboard_database


class ContextSensitivePredictor:
    """Test boundary whose output proves selected race context was forwarded."""

    def predict_race(
        self,
        *,
        race_date: date,
        distance_meters: int,
        surface: str,
        participants: tuple[object, ...],
    ) -> RealRacePrediction:
        del race_date, participants
        alpha = 0.7 if distance_meters == 1000 and surface == "arena" else 0.4
        wins = {"horse-1": alpha, "horse-2": 1.0 - alpha}
        return RealRacePrediction(
            win_probabilities=wins,
            place_probabilities={"horse-1": 1.0, "horse-2": 1.0},
            fair_odds={key: 1 / value for key, value in wins.items()},
            metadata=RealModelMetadata(
                model_type="historical_lightgbm_v1",
                training_rows=31_418,
                training_start=date(2024, 1, 6),
                training_end=date(2026, 11, 15),
                artifact_sha256="a" * 64,
            ),
            distance_meters=distance_meters,
            surface=surface,
        )


def test_prediction_service_uses_selected_race_context_and_real_provenance(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "dashboard.sqlite3"
    _create_dashboard_database(database_path)
    repository = DashboardRepository.open(database_path)
    try:
        race = repository.races_for_meeting("202647")[0]
        participants = repository.participants_for_race(race.id)
        service = PredictionService(ContextSensitivePredictor())

        sprint = service.for_race(race, participants)
        derby_context = RaceOption(
            id=race.id,
            meeting_code=race.meeting_code,
            race_number=10,
            scheduled_date=race.scheduled_date,
            distance_meters=2400,
            surface="arena",
        )
        derby = service.for_race(derby_context, participants)

        assert [row.horse_name for row in sprint.rows] == ["WAYTT", "REFUGIADO"]
        assert sprint.rows[0].win_probability == 0.7
        assert sprint.rows[0].fair_odds == 1 / 0.7
        assert derby.rows[0].win_probability == 0.4
        assert sprint.training_rows == 31_418
        assert sprint.provenance == (
            "Predicción generada por el modelo LightGBM entrenado con "
            "31,418 registros históricos (2024-2026)"
        )
    finally:
        repository.close()
