"""Historical features built from completed dates only."""

import pandas as pd  # type: ignore[import-untyped]

from benter_peru.ml.real_features import COLD_START_WIN_RATE


def _daily_totals(frame: pd.DataFrame, identity: list[str]) -> pd.DataFrame:
    keys = [*identity, "Fecha_Dt"]
    daily = frame.groupby(keys, sort=True).agg(
        wins=("Target_Ganador", "sum"),
        starts=("Target_Ganador", "size"),
        positions=("Posicion_Num", "sum"),
    )
    cumulative = (
        daily.groupby(level=list(range(len(identity)))).cumsum() if identity else (daily.cumsum())
    )
    return frame[keys].join(cumulative - daily, on=keys)


def clean_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Rebuild all 18 columns with day-level exclusion and no fitted encoding."""
    frame = raw.copy()
    frame["Fecha_Dt"] = pd.to_datetime(frame["Fecha"], errors="raise").dt.normalize()
    frame["Carrera_Num"] = pd.to_numeric(frame["Carrera"], errors="coerce").fillna(1)
    frame["Mandil_Num"] = pd.to_numeric(frame["Numero_Mandil"], errors="coerce").fillna(99)
    frame = frame.sort_values(["Fecha_Dt", "Carrera_Num", "Mandil_Num"], kind="stable").reset_index(
        drop=True
    )
    frame["Target_Ganador"] = (frame["Posicion"].astype(str).str.strip() == "1").astype(int)
    frame["Posicion_Num"] = pd.to_numeric(frame["Posicion"], errors="coerce").fillna(8.0)
    for source, target in (
        ("Caballo", "Caballo_Limpio"),
        ("Jinete", "Jinete_Limpio"),
        ("Preparador", "Prep_Limpio"),
        ("Stud", "Stud_Limpio"),
    ):
        frame[target] = frame[source].fillna("DESCONOCIDO").astype(str).str.strip()

    previous = _daily_totals(frame, [])
    prior = (previous["wins"] / previous["starts"].replace(0, float("nan"))).fillna(
        COLD_START_WIN_RATE
    )
    for keys, prefix, weight in (
        (["Jinete_Limpio"], "Jinete", 5.0),
        (["Prep_Limpio"], "Preparador", 5.0),
        (["Caballo_Limpio"], "Caballo", 2.0),
        (["Stud_Limpio"], "Stud", 5.0),
        (["Jinete_Limpio", "Prep_Limpio"], "Duo", 2.0),
    ):
        previous = _daily_totals(frame, keys)
        starts = previous["starts"]
        frame[f"{prefix}_WinRate_Smoothed"] = (previous["wins"] + weight * prior) / (
            starts + weight
        )
        if prefix in {"Jinete", "Preparador", "Caballo"}:
            frame[f"{prefix}_Carreras_Prev"] = starts
        if prefix == "Caballo":
            frame["Caballo_Puesto_Prom_Hist"] = (
                previous["positions"] / starts.replace(0, float("nan"))
            ).fillna(5.0)

    source_ages = frame.assign(age=pd.to_numeric(frame["Edad"], errors="coerce"))
    age_keys = ["Caballo_Limpio", "Fecha_Dt"]
    ages = source_ages.groupby(age_keys, sort=True)["age"].last()
    ages = ages.groupby(level=0).ffill().groupby(level=0).shift().rename("Edad_Num")
    frame["Edad_Num"] = frame[age_keys].join(ages, on=age_keys)["Edad_Num"].fillna(4.0)
    frame["Peso_Num"] = pd.to_numeric(
        frame["Peso"].astype(str).str.extract(r"(\d+(?:\.\d+)?)")[0], errors="coerce"
    ).fillna(55.0)
    distance = frame["Distancia"].astype(str).str.replace(r"(?<=\d)[.,](?=\d{3}\b)", "", regex=True)
    frame["Distancia_Num"] = pd.to_numeric(
        distance.str.extract(r"(\d+)")[0], errors="coerce"
    ).fillna(1000.0)
    frame["Competidores_Carrera"] = frame.groupby(["Fecha_Dt", "Carrera_Num"])["Caballo"].transform(
        "size"
    )
    frame["Prob_Base_Lote"] = 1.0 / frame["Competidores_Carrera"]
    return frame


def temporal_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    dates = sorted(frame["Fecha_Dt"].unique())
    if len(dates) < 2:
        raise ValueError("At least two distinct race dates are required")
    cutoff = pd.Timestamp(dates[int(len(dates) * 0.8)])
    return frame[frame["Fecha_Dt"] < cutoff], frame[frame["Fecha_Dt"] >= cutoff], cutoff
