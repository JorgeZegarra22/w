"""Benter Perú read-only Streamlit dashboard."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from benter_peru.ml.analyst import AnalystRunner, senior_analysis
from benter_peru.ml.artifacts import EnsembleArtifactConfig
from benter_peru.ml.betting import BettingError
from benter_peru.ml.models import (
    EnsembleRaceModel,
    ModelError,
    RealModelArtifactError,
)
from benter_peru.ml.pace import classify_pace
from benter_peru.ml.real_features import HistoricalFeatureError
from benter_peru.ui.pace_panel import load_race_video_styles, show_pace_panel
from benter_peru.ui.paths import project_path
from benter_peru.ui.queries import (
    DATABASE_ERROR_MESSAGE,
    DashboardDatabaseError,
    DashboardRepository,
    RaceOption,
)
from benter_peru.ui.service import (
    BettingStrategy,
    BettingStrategyService,
    DashboardPrediction,
    PredictionService,
    journalist_pick_labels,
)
from benter_peru.ui.ticket_panel import show_ticket_generator

ARTIFACT_ERROR_MESSAGE = (
    "Error: Artefactos del modelo no encontrados o corruptos. "
    "Por favor, ejecute el pipeline de entrenamiento."
)


@st.cache_resource
def _repository(database_path: str) -> DashboardRepository:
    return DashboardRepository.open(Path(database_path))


def _load_prediction_service(config: EnsembleArtifactConfig) -> PredictionService:
    model = EnsembleRaceModel.load(
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
        EnsembleArtifactConfig(
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

    snapshots = repository.horse_snapshots_for_race(race.id)
    video_styles = load_race_video_styles(
        race, dict(zip(frame["Mandil"], frame["Caballo"], strict=True))
    )
    for row in frame.to_dict(orient="records"):
        mandil = int(row["Mandil"])
        snapshot = snapshots.get(mandil)
        with st.expander(f"{mandil} · {row['Caballo']}"):
            video = video_styles.get(mandil)
            if video is not None and video.video_code:
                st.caption(
                    f"Video previo · Estela {video.drafting_label} · "
                    f"Desgaste por fuera {video.overground_penalty or '—'}"
                )
                if video.lane_position:
                    st.caption(video.lane_position)
            if snapshot is None:
                st.caption("Perfil oficial no disponible.")
                continue
            st.caption(f"Captura oficial · {snapshot.fetched_at:%d/%m/%Y %H:%M} UTC")
            form = snapshot.profile.get("recent_races")
            workouts = snapshot.profile.get("workouts")
            st.subheader("Última forma")
            if isinstance(form, list) and form:
                st.dataframe(pd.DataFrame.from_records(form[:5]), hide_index=True)
            else:
                st.caption("Sin carreras registradas en la captura.")
            st.subheader("Aprontes recientes")
            if isinstance(workouts, list) and workouts:
                st.dataframe(pd.DataFrame.from_records(workouts), hide_index=True)
            else:
                st.caption("Sin aprontes registrados en la captura.")


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
    pick_labels = journalist_pick_labels(
        horse_rows=tuple(
            (item.horse_id, item.mandil, item.horse_name) for item in participants
        ),
        picks=repository.journalist_picks_for_race(
            race.meeting_code, race.race_number
        ),
    )
    snapshots = repository.horse_snapshots_for_race(race.id)
    frame = pd.DataFrame.from_records(
        [
            {
                "Mandil": row.mandil,
                "Caballo": row.horse_name,
                "Pick del Periodista": pick_labels[row.participant_id],
                "Estilo": classify_pace(
                    snapshots[row.mandil].profile if row.mandil in snapshots else {}
                ).label,
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


def _parse_offered_odds(frame: pd.DataFrame) -> dict[str, float]:
    """Read only explicit, valid decimal quotes from an editor result."""
    offered: dict[str, float] = {}
    for row in frame.to_dict(orient="records"):
        raw_value = row.get("Cuota Real")
        if raw_value is None or pd.isna(raw_value):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise BettingError("Cuota Real debe ser un número decimal mayor que 1") from error
        if not pd.notna(value) or value <= 1 or value == float("inf"):
            raise BettingError("Cuota Real debe ser finita y mayor que 1")
        offered[str(row["participant_id"])] = value
    return offered


def _combination_frame(strategy: BettingStrategy, *, trifecta: bool) -> pd.DataFrame:
    combinations = strategy.trifectas if trifecta else strategy.exactas
    return pd.DataFrame.from_records(
        [
            {
                "Orden": " → ".join(item.horse_names),
                "Probabilidad Conjunta": item.joint_probability,
                "Dividendo Justo Teórico": item.fair_odds,
            }
            for item in combinations
        ]
    )


def _show_market_strategy(
    repository: DashboardRepository, prediction_service: PredictionService
) -> None:
    st.header("Estrategia de Apuestas")
    st.caption("En la versión web, las cuotas deben ingresarse manualmente")
    st.caption(
        "Las cuotas se usan solo en memoria. Sin cuota real no se calcula EV ni Kelly."
    )
    race = _select_race(repository)
    if race is None:
        return
    participants = repository.participants_for_race(race.id)
    if len(participants) < 2:
        st.info("Se necesitan al menos dos participantes para analizar la carrera.")
        return
    try:
        with st.spinner("Calculando probabilidades reales…"):
            prediction: DashboardPrediction = prediction_service.for_race(
                race, participants
            )
    except (HistoricalFeatureError, ModelError) as error:
        st.error(f"No fue posible calcular la estrategia: {error}")
        return

    st.subheader("📝 Pronóstico del Analista Senior")
    st.caption(prediction.provenance)
    analyst = st.empty()
    snapshots = repository.horse_snapshots_for_race(race.id)
    runners = [AnalystRunner(row.mandil, row.horse_name, row.win_probability)
               for row in prediction.rows]
    profiles = {mandil: snapshot.profile for mandil, snapshot in snapshots.items()}

    pick_labels = journalist_pick_labels(
        horse_rows=tuple(
            (item.horse_id, item.mandil, item.horse_name) for item in participants
        ),
        picks=repository.journalist_picks_for_race(
            race.meeting_code, race.race_number
        ),
    )
    editor_frame = pd.DataFrame.from_records(
        [
            {
                "participant_id": row.participant_id,
                "Mandil": row.mandil,
                "Caballo": row.horse_name,
                "Pick del Periodista": pick_labels[row.participant_id],
                "Prob. Ganar": row.win_probability,
                "Cuota Justa": row.fair_odds,
                "Cuota Real": None,
            }
            for row in prediction.rows
        ]
    )
    edited = st.data_editor(
        editor_frame,
        hide_index=True,
        width="stretch",
        disabled=[
            "participant_id",
            "Mandil",
            "Caballo",
            "Pick del Periodista",
            "Prob. Ganar",
            "Cuota Justa",
        ],
        column_config={
            "participant_id": None,
            "Prob. Ganar": st.column_config.NumberColumn(format="percent"),
            "Cuota Justa": st.column_config.NumberColumn(format="%.2f"),
            "Cuota Real": st.column_config.NumberColumn(
                min_value=1.01, format="%.2f", help="Dividendo decimal ofrecido"
            ),
        },
        key=f"market-quotes-{race.id}",
    )
    strategy_service = BettingStrategyService()
    ticket = show_ticket_generator(repository, prediction_service, race, prediction)
    try:
        offered = _parse_offered_odds(edited)
    except BettingError as error:
        st.error(str(error))
        offered = {}
    analyst.text(senior_analysis(
        race.race_number, runners, profiles,
        {row.mandil: offered[row.participant_id] for row in prediction.rows
         if row.participant_id in offered}, ticket,
    ))
    theoretical = strategy_service.analyze(prediction, {})
    st.subheader("Top 3 Exactas")
    st.caption("Probabilidades y dividendos justos teóricos; no son recomendaciones.")
    st.dataframe(
        _combination_frame(theoretical, trifecta=False),
        hide_index=True,
        width="stretch",
        column_config={
            "Probabilidad Conjunta": st.column_config.NumberColumn(format="percent"),
            "Dividendo Justo Teórico": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    if theoretical.trifectas:
        st.subheader("Top 3 Trifectas")
        st.caption(
            "Probabilidades y dividendos justos teóricos; no son recomendaciones."
        )
        st.dataframe(
            _combination_frame(theoretical, trifecta=True),
            hide_index=True,
            width="stretch",
            column_config={
                "Probabilidad Conjunta": st.column_config.NumberColumn(
                    format="percent"
                ),
                "Dividendo Justo Teórico": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    if not st.button("Analizar Valor", type="primary"):
        return
    try:
        offered = _parse_offered_odds(edited)
        strategy = strategy_service.analyze(prediction, offered)
    except BettingError as error:
        st.error(str(error))
        return
    if not strategy.has_market_quotes:
        st.info("Sin recomendación: ingrese al menos una cuota real de mercado.")
        return
    assessment_frame = pd.DataFrame.from_records(
        [
            {
                "Caballo": row.horse_name,
                "Cuota Justa": row.fair_odds,
                "Cuota Real": row.offered_odds,
                "EV": row.expected_value,
                "% Bankroll Sugerido": row.kelly_stake,
                "Tiene Valor": row.has_value,
            }
            for row in strategy.win_assessments
        ]
    )
    st.subheader("Análisis Ganador")
    st.dataframe(
        assessment_frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Cuota Justa": st.column_config.NumberColumn(format="%.2f"),
            "Cuota Real": st.column_config.NumberColumn(format="%.2f"),
            "EV": st.column_config.NumberColumn(format="percent"),
            "% Bankroll Sugerido": st.column_config.NumberColumn(format="percent"),
        },
    )
    valuable = [row for row in strategy.win_assessments if row.has_value]
    if valuable:
        best = max(valuable, key=lambda row: row.kelly_stake)
        st.success(
            f"Apuesta base: {best.horse_name}. "
            f"Stake sugerido: {best.kelly_stake:.2%} del bankroll."
        )
    else:
        st.info("No apostar: ninguna cuota ingresada ofrece valor esperado positivo.")


def main() -> None:
    st.set_page_config(page_title="Benter Perú", page_icon="🐎", layout="wide")
    st.title("Benter Perú")
    st.caption("Inteligencia hípica auditable · dashboard de solo lectura")
    database_path = project_path(os.environ.get("BENTER_DATABASE_PATH", "var/benter.sqlite3"))
    try:
        repository = _repository(str(database_path))
    except DashboardDatabaseError:
        st.error(DATABASE_ERROR_MESSAGE)
        st.info("Configura una copia SQLite de solo lectura para esta instalación.")
        st.stop()
        return
    artifact_config = EnsembleArtifactConfig.from_env()
    try:
        prediction_service = _prediction_service(
            str(project_path(artifact_config.model_path)),
            str(project_path(artifact_config.dataset_path)),
            artifact_config.expected_sha256,
        )
    except RealModelArtifactError:
        st.error(ARTIFACT_ERROR_MESSAGE)
        st.info("Comprueba que el modelo y el dataset histórico estén disponibles en el servidor.")
        st.stop()
        return

    view = st.sidebar.radio(
        "Navegación",
        ("Resumen", "Carreras", "Predicciones", "Estrategia de Apuestas", "Simulación de Ritmo"),
    )
    st.sidebar.caption("SQLite · modo de solo lectura")
    if view == "Resumen":
        _show_summary(repository)
    elif view == "Carreras":
        _show_races(repository)
    elif view == "Predicciones":
        _show_predictions(repository, prediction_service)
    elif view == "Estrategia de Apuestas":
        _show_market_strategy(repository, prediction_service)
    else:
        st.header("Simulación de Ritmo")
        race = _select_race(repository)
        if race is not None:
            show_pace_panel(repository, prediction_service, race)


if __name__ == "__main__":
    main()
