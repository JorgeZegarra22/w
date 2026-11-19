"""Print a reproducible strategy example using invented Derby market prices."""

from __future__ import annotations

import json
from typing import TypedDict

from benter_peru.ui.service import (
    BettingStrategyService,
    DashboardPrediction,
    PredictionRow,
)


class AssessmentOutput(TypedDict):
    horse: str
    fair_odds: float
    offered_odds: float
    expected_value: float
    kelly_stake: float


class CombinationOutput(TypedDict):
    order: tuple[str, ...]
    joint_probability: float
    fair_odds: float


class SimulationOutput(TypedDict):
    warning: str
    win_assessments: list[AssessmentOutput]
    top_exactas: list[CombinationOutput]
    top_trifectas: list[CombinationOutput]


_RUNNERS = (
    ("shotra", 1, "SHOTRA", 0.14033941396300373),
    ("pergaminos", 2, "LOS PERGAMINOS", 0.12595159624278013),
    ("peggy", 3, "MR. PEGGY", 0.19608583586519554),
    ("sabelon", 4, "MR. SABELON", 0.10649041921246567),
    ("lindo", 5, "VIEJO LINDO", 0.19170386712159393),
    ("scott", 6, "MR. SCOTT", 0.13613894713219346),
    ("kimby", 7, "MARAVILLA KIMBY", 0.10328992046276753),
)
_INVENTED_ODDS = {
    "shotra": 8.5,
    "pergaminos": 7.0,
    "peggy": 3.5,
    "sabelon": 9.0,
    "lindo": 5.8,
    "scott": 8.0,
    "kimby": 10.0,
}


def build_simulation() -> SimulationOutput:
    prediction = DashboardPrediction(
        rows=tuple(
            PredictionRow(
                participant_id=participant_id,
                mandil=mandil,
                horse_name=horse_name,
                win_probability=probability,
                top_three_probability=0.0,
                fair_odds=1.0 / probability,
            )
            for participant_id, mandil, horse_name, probability in _RUNNERS
        ),
        provenance="Simulación con probabilidades históricas del modelo real",
        training_rows=31_418,
    )
    strategy = BettingStrategyService().analyze(prediction, _INVENTED_ODDS)
    return {
        "warning": (
            "CUOTAS INVENTADAS PARA VALIDACION; NO SON PRECIOS DE MERCADO "
            "NI UNA RECOMENDACION REAL."
        ),
        "win_assessments": [
            {
                "horse": row.horse_name,
                "fair_odds": row.fair_odds,
                "offered_odds": row.offered_odds,
                "expected_value": row.expected_value,
                "kelly_stake": row.kelly_stake,
            }
            for row in strategy.win_assessments
        ],
        "top_exactas": [
            {
                "order": row.horse_names,
                "joint_probability": row.joint_probability,
                "fair_odds": row.fair_odds,
            }
            for row in strategy.exactas
        ],
        "top_trifectas": [
            {
                "order": row.horse_names,
                "joint_probability": row.joint_probability,
                "fair_odds": row.fair_odds,
            }
            for row in strategy.trifectas
        ],
    }


def main() -> None:
    print(json.dumps(build_simulation(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
