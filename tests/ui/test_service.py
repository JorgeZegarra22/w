"""Dashboard prediction composition tests."""

from pathlib import Path

from benter_peru.ui.queries import DashboardRepository
from benter_peru.ui.service import MODEL_WARNING, PredictionService

from .test_queries import _create_dashboard_database


def test_prediction_service_calculates_race_probabilities(tmp_path: Path) -> None:
    database_path = tmp_path / "dashboard.sqlite3"
    _create_dashboard_database(database_path)
    repository = DashboardRepository.open(database_path)
    try:
        race = repository.races_for_meeting("202647")[0]
        participants = repository.participants_for_race(race.id)

        result = PredictionService(repository.engine).for_race(race, participants)

        assert [row.horse_name for row in result.rows] == ["WAYTT", "REFUGIADO"]
        assert sum(row.win_probability for row in result.rows) == 1.0
        assert sum(row.top_three_probability for row in result.rows) == 2.0
        assert all(row.top_three_probability == 1.0 for row in result.rows)
        assert result.warning == MODEL_WARNING
        assert "NO CALIBRADO" in result.warning
    finally:
        repository.close()
