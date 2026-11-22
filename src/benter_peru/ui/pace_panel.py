"""Race-scoped controls for exploring Monte Carlo pace scenarios."""

import os
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from benter_peru.ml.models import ModelError
from benter_peru.ml.pace import PaceStyle, classify_pace
from benter_peru.ml.real_features import HistoricalFeatureError
from benter_peru.ml.simulator import (
    COLLISION_LEADERS,
    FINAL_STRETCH_METERS,
    PaceParticipant,
    count_leaders,
    simulate_race,
)
from benter_peru.ml.video_pace import load_video_styles
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
    styles_path = Path(os.environ.get("BENTER_PACE_STYLES_PATH", "estilos_domingo_2026.csv"))
    try:
        video_styles = (
            load_video_styles(
                styles_path.read_text(encoding="utf-8-sig"),
                race.scheduled_date,
                race.race_number,
                {item.mandil: item.horse_name for item in entrants},
            )
            if styles_path.is_file()
            else {}
        )
    except (OSError, ValueError) as error:
        st.warning(f"Estilos de video no disponibles para esta carrera. {error}")
        video_styles = {}
    snapshots = repository.horse_snapshots_for_race(race.id)
    assessments = {
        item.mandil: classify_pace(
            snapshots[item.mandil].profile if item.mandil in snapshots else {}
        )
        for item in entrants
    }
    st.caption(
        "El simulador usa parámetros tácticos hipotéticos."
        + (
            f" La biomecánica aplica un ajuste sin calibración en los últimos "
            f"{FINAL_STRETCH_METERS} m."
            if video_styles
            else ""
        )
    )
    overrides: dict[int, PaceStyle] = {}
    with st.form(f"pace-form-{race.id}"):
        for item in entrants:
            if video_styles:
                video_style = video_styles[item.mandil]
                stride = video_style.stride_frequency
                details = f" · {stride:.2f} zancadas/s" if stride is not None else ""
                if video_style.fatigue_factor:
                    details += f" · {video_style.fatigue_factor}"
                st.write(f"{item.mandil} · {item.horse_name} · {video_style.label}{details}")
                overrides[item.mandil] = video_style.style
                continue
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
                video_style.fatigue_factor if video_style else None,
                video_style.stride_drop_pct if video_style else None,
            )
            for row in prediction.rows
            for video_style in (video_styles.get(row.mandil),)
        ]
        pace = simulate_race(participants, include_biomechanics=False)
        adjusted = simulate_race(participants) if video_styles else pace
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
                    video_styles[row.mandil].label
                    if video_styles
                    else f"{overrides[row.mandil].value.capitalize()} · manual"
                    if row.mandil in overrides
                    else assessments[row.mandil].label
                ),
                "Prob. Ensamble": row.win_probability,
                "Prob. ajustada por ritmo": pace[row.participant_id],
                **(
                    {
                        "Zancadas/s": video_styles[row.mandil].stride_frequency,
                        "Factor de fatiga": video_styles[row.mandil].fatigue_factor or "—",
                        "Prob. ritmo + biomecánica": adjusted[row.participant_id],
                    }
                    if video_styles
                    else {}
                ),
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
            for column in (
                "Prob. Ensamble",
                "Prob. ajustada por ritmo",
                "Prob. ritmo + biomecánica",
            )
        },
    )
