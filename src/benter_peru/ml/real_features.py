"""Historical feature construction for the real LightGBM race model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from benter_peru.entities.normalization import normalize_name

LIGHTGBM_FEATURE_COLUMNS = (
    "Jinete_WinRate_Smoothed",
    "Jinete_Carreras_Prev",
    "Preparador_WinRate_Smoothed",
    "Preparador_Carreras_Prev",
    "Caballo_WinRate_Smoothed",
    "Caballo_Carreras_Prev",
    "Caballo_Puesto_Prom_Hist",
    "Stud_WinRate_Smoothed",
    "Duo_WinRate_Smoothed",
    "Peso_Num",
    "Distancia_Num",
    "Edad_Num",
    "Mandil_Num",
    "Competidores_Carrera",
    "Prob_Base_Lote",
    "Jinete_Limpio",
    "Prep_Limpio",
    "Stud_Limpio",
)
CATEGORICAL_FEATURE_COLUMNS = ("Jinete_Limpio", "Prep_Limpio", "Stud_Limpio")
_REQUIRED_DATASET_COLUMNS = frozenset(
    {"Fecha", "Posicion", "Caballo", "Jinete", "Preparador", "Stud", "Edad"}
)

type LightGBMFeatureValue = float | str
type LightGBMFeatureRow = dict[str, LightGBMFeatureValue]


class HistoricalFeatureError(ValueError):
    """Raised when trustworthy historical features cannot be constructed."""


@dataclass(frozen=True, slots=True)
class RealRaceParticipant:
    participant_id: str
    horse_name: str
    jockey_name: str
    trainer_name: str
    stud_name: str
    weight: float
    mandil: int


class HistoricalLightGBMFeatureEngine:
    """Build the fitted model's exact feature frame without date leakage."""

    def __init__(self, dataset_path: Path) -> None:
        if not dataset_path.is_file():
            raise HistoricalFeatureError(f"historical dataset not found: {dataset_path}")
        frame = pd.read_csv(dataset_path)
        missing = sorted(_REQUIRED_DATASET_COLUMNS.difference(frame.columns))
        if missing:
            raise HistoricalFeatureError(
                f"historical dataset missing columns: {', '.join(missing)}"
            )
        frame = frame.copy()
        frame["Fecha_Dt"] = pd.to_datetime(frame["Fecha"], errors="coerce")
        if frame["Fecha_Dt"].isna().any():
            raise HistoricalFeatureError("historical dataset contains invalid dates")
        for column in ("Caballo", "Jinete", "Preparador", "Stud"):
            frame[column] = frame[column].fillna("DESCONOCIDO").astype(str).str.strip()
        frame["Target_Ganador"] = (
            frame["Posicion"].astype(str).str.strip() == "1"
        ).astype(int)
        frame["Posicion_Num"] = pd.to_numeric(frame["Posicion"], errors="coerce").fillna(
            8.0
        )
        frame["Edad_Num"] = pd.to_numeric(frame["Edad"], errors="coerce")
        self._frame = frame

    @property
    def row_count(self) -> int:
        return len(self._frame)

    @property
    def date_range(self) -> tuple[date, date]:
        return (
            self._frame["Fecha_Dt"].min().date(),
            self._frame["Fecha_Dt"].max().date(),
        )

    def for_race(
        self,
        *,
        race_date: date,
        distance_meters: int,
        surface: str,
        participants: tuple[RealRaceParticipant, ...],
        global_win_rate: float,
    ) -> dict[str, LightGBMFeatureRow]:
        if distance_meters <= 0:
            raise HistoricalFeatureError("distance_meters must be positive")
        if surface not in {"arena", "cesped"}:
            raise HistoricalFeatureError("surface must be arena or cesped")
        if len(participants) < 1:
            raise HistoricalFeatureError("race must contain participants")
        if not 0 <= global_win_rate <= 1:
            raise HistoricalFeatureError("global_win_rate must be between zero and one")
        participant_ids = [participant.participant_id for participant in participants]
        if any(not value for value in participant_ids) or len(set(participant_ids)) != len(
            participant_ids
        ):
            raise HistoricalFeatureError("participant IDs must be nonempty and unique")

        history = self._frame[self._frame["Fecha_Dt"] < pd.Timestamp(race_date)]
        field_size = len(participants)
        rows: dict[str, LightGBMFeatureRow] = {}
        for participant in participants:
            horse_name = self._resolve_identity(
                history, "Caballo", participant.horse_name, strict=True
            )
            jockey_name = self._resolve_identity(
                history, "Jinete", participant.jockey_name, strict=False
            )
            trainer_name = self._resolve_identity(
                history, "Preparador", participant.trainer_name, strict=False
            )
            stud_name = self._resolve_identity(
                history, "Stud", participant.stud_name, strict=False
            )
            horse_rows = history[history["Caballo"] == horse_name]
            if horse_rows.empty:
                raise HistoricalFeatureError(
                    f"{participant.horse_name} has no prior history"
                )
            latest = horse_rows.sort_values("Fecha_Dt").iloc[-1]
            age = latest["Edad_Num"]
            if pd.isna(age):
                raise HistoricalFeatureError(
                    f"{participant.horse_name} has no valid prior age"
                )
            jockey_rows = history[history["Jinete"] == jockey_name]
            trainer_rows = history[history["Preparador"] == trainer_name]
            stud_rows = history[history["Stud"] == stud_name]
            duo_rows = history[
                (history["Jinete"] == jockey_name)
                & (history["Preparador"] == trainer_name)
            ]
            j_rate, j_starts = self._smoothed(jockey_rows, global_win_rate, 5.0)
            p_rate, p_starts = self._smoothed(trainer_rows, global_win_rate, 5.0)
            c_rate, c_starts = self._smoothed(horse_rows, global_win_rate, 2.0)
            s_rate, _ = self._smoothed(stud_rows, global_win_rate, 5.0)
            duo_rate, _ = self._smoothed(duo_rows, global_win_rate, 2.0)
            values: tuple[LightGBMFeatureValue, ...] = (
                j_rate,
                j_starts,
                p_rate,
                p_starts,
                c_rate,
                c_starts,
                float(horse_rows["Posicion_Num"].mean()),
                s_rate,
                duo_rate,
                float(participant.weight),
                float(distance_meters),
                float(age),
                float(participant.mandil),
                float(field_size),
                1.0 / field_size,
                jockey_name,
                trainer_name,
                stud_name,
            )
            rows[participant.participant_id] = dict(
                zip(LIGHTGBM_FEATURE_COLUMNS, values, strict=True)
            )
        return rows

    @staticmethod
    def _smoothed(
        rows: pd.DataFrame, global_win_rate: float, prior_weight: float
    ) -> tuple[float, float]:
        starts = float(len(rows))
        wins = float(rows["Target_Ganador"].sum())
        rate = (wins + prior_weight * global_win_rate) / (starts + prior_weight)
        return rate, starts

    @staticmethod
    def _resolve_identity(
        history: pd.DataFrame,
        column: str,
        observed: str,
        *,
        strict: bool,
    ) -> str:
        value = observed.strip()
        values = tuple(str(item) for item in history[column].dropna().unique())
        if value in values:
            return value
        normalized = normalize_name(value)
        matches = tuple(item for item in values if normalize_name(item) == normalized)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            entity = "horse" if column == "Caballo" else column.lower()
            raise HistoricalFeatureError(f"ambiguous {entity} identity: {observed}")
        if strict:
            raise HistoricalFeatureError(f"{observed} has no prior history")
        return value
