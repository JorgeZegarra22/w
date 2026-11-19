"""In-memory prediction composition for the read-only dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from benter_peru.ml.betting import (
    BettingError,
    OrderedCombination,
    calculate_expected_value,
    calculate_kelly_stake,
    generate_top_combinations,
)
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
    participant_id: str
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


@dataclass(frozen=True, slots=True)
class WinValueRow:
    participant_id: str
    mandil: int
    horse_name: str
    fair_odds: float
    offered_odds: float
    expected_value: float
    kelly_stake: float
    has_value: bool


@dataclass(frozen=True, slots=True)
class NamedCombination:
    bet_type: str
    participant_ids: tuple[str, ...]
    horse_names: tuple[str, ...]
    joint_probability: float
    fair_odds: float


@dataclass(frozen=True, slots=True)
class BettingStrategy:
    win_assessments: tuple[WinValueRow, ...]
    exactas: tuple[NamedCombination, ...]
    trifectas: tuple[NamedCombination, ...]
    has_market_quotes: bool


class BettingStrategyService:
    """Compose explicit win quotes and theoretical ordered combinations."""

    def analyze(
        self,
        prediction: DashboardPrediction,
        offered_win_odds: dict[str, float] | None = None,
    ) -> BettingStrategy:
        offered = offered_win_odds or {}
        rows_by_id = {row.participant_id: row for row in prediction.rows}
        unknown = set(offered) - set(rows_by_id)
        if unknown:
            raise BettingError(
                f"unknown participant in win odds: {sorted(unknown)[0]}"
            )
        assessments: list[WinValueRow] = []
        for row in prediction.rows:
            if row.participant_id not in offered:
                continue
            odds = offered[row.participant_id]
            expected_value = calculate_expected_value(row.win_probability, odds)
            kelly_stake = calculate_kelly_stake(row.win_probability, odds)
            assessments.append(
                WinValueRow(
                    participant_id=row.participant_id,
                    mandil=row.mandil,
                    horse_name=row.horse_name,
                    fair_odds=row.fair_odds,
                    offered_odds=odds,
                    expected_value=expected_value,
                    kelly_stake=kelly_stake,
                    has_value=expected_value > 0,
                )
            )
        probabilities = {
            row.participant_id: row.win_probability for row in prediction.rows
        }
        exactas = self._named_combinations(
            prediction, generate_top_combinations(probabilities, "exacta", 3)
        )
        trifectas = (
            self._named_combinations(
                prediction,
                generate_top_combinations(probabilities, "trifecta", 3),
            )
            if len(prediction.rows) >= 3
            else ()
        )
        return BettingStrategy(
            win_assessments=tuple(assessments),
            exactas=exactas,
            trifectas=trifectas,
            has_market_quotes=bool(offered),
        )

    @staticmethod
    def _named_combinations(
        prediction: DashboardPrediction,
        combinations: tuple[OrderedCombination, ...],
    ) -> tuple[NamedCombination, ...]:
        names = {row.participant_id: row.horse_name for row in prediction.rows}
        result: list[NamedCombination] = []
        for combination in combinations:
            result.append(
                NamedCombination(
                    bet_type=combination.bet_type,
                    participant_ids=combination.participant_ids,
                    horse_names=tuple(
                        names[participant_id]
                        for participant_id in combination.participant_ids
                    ),
                    joint_probability=combination.joint_probability,
                    fair_odds=combination.fair_odds,
                )
            )
        return tuple(result)


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
                participant_id=participant.horse_id,
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
