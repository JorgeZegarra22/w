"""Benter Perú read-only Streamlit dashboard."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from benter_peru.ml.artifacts import RealModelArtifactConfig
from benter_peru.ml.models import (
    ModelError,
    RealLightGBMRaceModel,
    RealModelArtifactError,
)
from benter_peru.ml.real_features import HistoricalFeatureError
from benter_peru.ui.queries import (
    DATABASE_ERROR_MESSAGE,
    DashboardDatabaseError,
    DashboardRepository,
    RaceOption,
)
from benter_peru.ui.service import PredictionService

ARTIFACT_ERROR_MESSAGE = (
    "Error: Artefactos del modelo no encontrados o corruptos. "
    "Por favor, ejecute el pipeline de entrenamiento."
)


@st.cache_resource
def _repository(database_path: str) -> DashboardRepository:
    return DashboardRepository.open(Path(database_path))


def _load_prediction_service(config: RealModelArtifactConfig) -> PredictionService:
    model = RealLightGBMRaceModel.load(
        model_path=config.model_path,
        dataset_path=config.dataset_path,
        expected_sha256=config.expected_sha256,
    )
    return PredictionService(model)


@st.cache_resource
def _prediction_service(
    model_path: str, dataset_path: str, expected_sha256: str
) -> PredictionService:
    return _load_prediction_service(
        RealModelArtifactConfig(
            model_path=Path(model_path),
            dataset_path=Path(dataset_path),
            expected_sha256=expected_sha256,
        )
    )


def _select_race(repository: DashboardRepository) -> RaceOption | None:
    meeting_codes = repository.meeting_codes()
    if not meeting_codes:
        st.info("Todavía no hay reuniones registradas.")
        return None
    meeting_code = st.selectbox("Reunión", meeting_codes)
    if meeting_code is None:
        return None
    race_options = repository.races_for_meeting(meeting_code)
    if not race_options:
        st.info("La reunión seleccionada no tiene carreras registradas.")
        return None
    return st.selectbox(
        "Carrera",
        race_options,
        format_func=lambda race: (
            f"Carrera {race.race_number} · {race.distance_meters} m · {race.surface}"
        ),
    )


def _participant_frame(repository: DashboardRepository, race: RaceOption) -> pd.DataFrame:
    participants = repository.participants_for_race(race.id)
    return pd.DataFrame.from_records(
        [
            {
                "Mandil": participant.mandil,
                "Caballo": participant.horse_name,
                "Jinete": participant.jockey_name,
                "Preparador": participant.trainer_name,
                "Stud": participant.stud_name,
                "Peso": participant.weight,
            }
            for participant in participants
        ]
    )


def _show_summary(repository: DashboardRepository) -> None:
    st.header("Resumen")
    summary = repository.summary()
    horses_column, races_column, facts_column = st.columns(3)
    horses_column.metric("Total caballos", summary.horses_total)
    races_column.metric("Total carreras", summary.races_total)
    facts_column.metric("Total hechos extraídos", summary.facts_total)


def _show_races(repository: DashboardRepository) -> None:
    st.header("Carreras")
    race = _select_race(repository)
    if race is None:
        return
    frame = _participant_frame(repository, race)
    if frame.empty:
        st.info("La carrera seleccionada no tiene participantes registrados.")
        return
    st.dataframe(frame, hide_index=True, width="stretch")


def _show_predictions(
    repository: DashboardRepository, prediction_service: PredictionService
) -> None:
    st.header("Predicciones")
    race = _select_race(repository)
    if race is None:
        return
    participants = repository.participants_for_race(race.id)
    if len(participants) < 2:
        st.info("Se necesitan al menos dos participantes para calcular un pronóstico.")
        return
    if not st.button("Calcular Pronóstico", type="primary"):
        return
    try:
        with st.spinner("Calculando características y probabilidades…"):
            result = prediction_service.for_race(race, participants)
    except (HistoricalFeatureError, ModelError) as error:
        st.error(f"No fue posible calcular el pronóstico: {error}")
        return
    frame = pd.DataFrame.from_records(
        [
            {
                "Mandil": row.mandil,
                "Caballo": row.horse_name,
                "Prob. Ganar": row.win_probability,
                "Prob. Placé (Top 3)": row.top_three_probability,
                "Dividendo Justo": row.fair_odds,
            }
            for row in result.rows
        ]
    )
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Prob. Ganar": st.column_config.NumberColumn(format="percent"),
            "Prob. Placé (Top 3)": st.column_config.NumberColumn(format="percent"),
            "Dividendo Justo": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.info(result.provenance)


def main() -> None:
    st.set_page_config(page_title="Benter Perú", page_icon="🐎", layout="wide")
    st.title("Benter Perú")
    st.caption("Inteligencia hípica auditable · dashboard de solo lectura")
    database_path = os.environ.get("BENTER_DATABASE_PATH", "var/benter.sqlite3")
    try:
        repository = _repository(database_path)
    except DashboardDatabaseError:
        st.error(DATABASE_ERROR_MESSAGE)
        st.stop()
        return
    artifact_config = RealModelArtifactConfig.from_env()
    try:
        prediction_service = _prediction_service(
            str(artifact_config.model_path),
            str(artifact_config.dataset_path),
            artifact_config.expected_sha256,
        )
    except RealModelArtifactError:
        st.error(ARTIFACT_ERROR_MESSAGE)
        st.stop()
        return

    view = st.sidebar.radio("Navegación", ("Resumen", "Carreras", "Predicciones"))
    st.sidebar.caption("SQLite · modo de solo lectura")
    if view == "Resumen":
        _show_summary(repository)
    elif view == "Carreras":
        _show_races(repository)
    else:
        _show_predictions(repository, prediction_service)


if __name__ == "__main__":
    main()
