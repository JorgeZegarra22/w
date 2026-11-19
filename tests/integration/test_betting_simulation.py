"""Reproducible invented-odds strategy simulation."""

from scripts.simulate_betting_strategy import build_simulation


def test_derby_simulation_uses_production_ev_kelly_and_combinations() -> None:
    result = build_simulation()

    rows = {row["horse"]: row for row in result["win_assessments"]}
    assert rows["MR. PEGGY"]["offered_odds"] == 3.5
    assert rows["MR. PEGGY"]["kelly_stake"] == 0.0
    assert rows["SHOTRA"]["offered_odds"] == 8.5
    assert rows["SHOTRA"]["expected_value"] > 0
    assert rows["SHOTRA"]["kelly_stake"] > 0
    assert len(result["top_exactas"]) == 3
    assert len(result["top_trifectas"]) == 3
    assert all("fair_odds" in item for item in result["top_exactas"])
