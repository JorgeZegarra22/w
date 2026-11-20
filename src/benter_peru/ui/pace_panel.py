"""Race-scoped controls for exploring Monte Carlo pace scenarios."""

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from benter_peru.ml.models import ModelError
from benter_peru.ml.pace import PaceStyle, classify_pace
from benter_peru.ml.real_features import HistoricalFeatureError
from benter_peru.ml.simulator import (
    COLLISION_LEADERS,
    PaceParticipant,
    count_leaders,
    simulate_race,
)
from benter_peru.ui.queries import DashboardRepository, RaceOption
from benter_peru.ui.service import PredictionService

_AUTOMATIC = "Automático"
_STYLE_OPTIONS = {_AUTOMATIC: None, **{style.value.capitalize(): style for style in PaceStyle}}


def show_pace_panel(
    repository: DashboardRepository, prediction_service: PredictionService, race: RaceOption
) -> None:
    entrants = repository.participants_for_race(race.id)
    if len(entrants) < 2:
        st.info("Se necesitan al menos dos participantes para simular la carrera.")
        return
    snapshots = repository.horse_snapshots_for_race(race.id)
    assessments = {
        item.mandil: classify_pace(
            snapshots[item.mandil].profile if item.mandil in snapshots else {}
        )
        for item in entrants
    }
    st.caption("Escenario táctico con parámetros hipotéticos. Los estilos manuales son supuestos.")
    overrides: dict[int, PaceStyle] = {}
    with st.form(f"pace-form-{race.id}"):
        for item in entrants:
            assessment = assessments[item.mandil]
            labels = {label: label for label in _STYLE_OPTIONS}
            labels[_AUTOMATIC] = f"Automático · {assessment.label}"
            selected = st.selectbox(
                f"{item.mandil} · {item.horse_name}",
                tuple(_STYLE_OPTIONS),
                key=f"pace-style-{race.id}-{item.mandil}",
                format_func=labels.__getitem__,
            )
            override = _STYLE_OPTIONS.get(selected or _AUTOMATIC)
            if override is not None:
                overrides[item.mandil] = override
        submitted = st.form_submit_button("Simular 10,000 carreras", type="primary")
    if not submitted:
        return
    try:
        prediction = prediction_service.for_race(race, entrants)
        participants = [
            PaceParticipant(
                row.participant_id,
                row.win_probability,
                overrides.get(row.mandil, assessments[row.mandil].style),
            )
            for row in prediction.rows
        ]
        adjusted = simulate_race(participants)
    except (HistoricalFeatureError, ModelError, ValueError) as error:
        st.error(f"No fue posible simular la carrera. {error}")
        return

    leaders = count_leaders(participants)
    if leaders >= COLLISION_LEADERS:
        closers = ", ".join(
            row.horse_name
            for row, runner in zip(prediction.rows, participants, strict=True)
            if runner.style == PaceStyle.CERRADOR
        )
        bonus = f" El escenario bonifica a {closers}." if closers else ""
        st.warning(f"⚠️ Colisión de Ritmo · {leaders} punteros en el escenario.{bonus}")
    else:
        st.info(f"El escenario tiene {leaders} punteros. El ajuste de ritmo queda inactivo.")
    frame = pd.DataFrame.from_records(
        [
            {
                "Mandil": row.mandil,
                "Caballo": row.horse_name,
                "Estilo": (
                    f"{overrides[row.mandil].value.capitalize()} · manual"
                    if row.mandil in overrides
                    else assessments[row.mandil].label
                ),
                "Prob. Ensamble": row.win_probability,
                "Prob. ajustada por ritmo": adjusted[row.participant_id],
            }
            for row in prediction.rows
        ]
    )
    st.subheader("Probabilidades por Simulación (Monte Carlo)")
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            column: st.column_config.NumberColumn(format="percent")
            for column in ("Prob. Ensamble", "Prob. ajustada por ritmo")
        },
    )
