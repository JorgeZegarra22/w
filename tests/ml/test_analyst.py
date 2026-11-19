from benter_peru.ml.analyst import AnalystRunner, senior_analysis


def test_favorite_and_positive_value_can_be_different() -> None:
    runners = [AnalystRunner(1, "A", 0.7), AnalystRunner(2, "B", 0.3)]
    snapshot = {
        1: {
            "recent_races": [{"date": "02Nov26", "position": "1°/5"}],
            "workouts": [{"date": "17Nov26", "distance_meters": 400, "time": "0.23.0"}],
        }
    }
    result = senior_analysis(10, runners, snapshot, {2: 4.0})
    assert "Favorito del modelo: 1 · A" in result
    assert "Apuesta con Valor (+EV): 2 · B" in result
    assert "0.23.0" in result
    assert "02Nov26" in result
    assert "fatiga" not in result


def test_no_bet_claim_without_market_prices() -> None:
    result = senior_analysis(1, [AnalystRunner(1, "A", 1.0)], {}, {})
    assert "Sin cuotas" in result
    assert "Apuesta con Valor (+EV)" not in result
