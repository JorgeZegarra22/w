# Real LightGBM Model Integration Design

**Status:** Approved for implementation  
**Date:** 2026-11-18  
**Target branch:** `codex/entregable-8-real-model-integration`

## 1. Objective

Replace the Streamlit prediction view's synthetic baseline with the trusted
`modelo_hipico_v1.pkl` LightGBM classifier trained from 31,418 Monterrico result
rows dated 2024-01-06 through 2026-11-15. The dashboard remains read-only and
must fail closed when either artifact is missing, altered, incompatible, or
insufficient for a selected race.

The synthetic baseline remains available to existing non-dashboard callers and
tests. There is no automatic or silent fallback from the real model.

## 2. Local Artifact Layout and Trust Boundary

The source Sandbox files are integrated as follows:

- `var/ml/real-model/modelo_hipico_v1.pkl`
- `var/ml/real-model/dataset_oficial_resultados.csv`
- `src/benter_peru/ml/entrenar_modelo.py`
- `src/benter_peru/ml/predecir_derby.py`

`var/` is already ignored. `.gitignore` additionally blocks
`dataset_oficial_resultados*.csv` and `*.pkl` so an artifact cannot be committed
after relocation. Python source is refactored into typed project modules rather
than copied as an unvalidated standalone script.

Pickle is an executable serialization format. Runtime loading is permitted only
after SHA-256 verification against this version-pinned digest:

```text
18c751b283a5af4461e5f9c16604e135bf56b00d0241f3f6c6c14e7d4537852f
```

The artifact came from the user-authorized local Sandbox. A different artifact
requires a code-reviewed digest change; merely changing the path does not grant
trust.

## 3. Runtime Configuration

The dashboard reads:

- `BENTER_DATABASE_PATH`, unchanged.
- `BENTER_REAL_MODEL_PATH`, default
  `var/ml/real-model/modelo_hipico_v1.pkl`.
- `BENTER_REAL_DATASET_PATH`, default
  `var/ml/real-model/dataset_oficial_resultados.csv`.

The expected digest is a source-controlled v1 constant, not an environment
default. The UI may cache a validated model service by the three resolved input
paths, but it never writes model state or predictions.

## 4. Historical Feature Contract

`HistoricalLightGBMFeatureEngine` loads and validates the CSV once. It requires
the raw columns used by training, parses `Fecha`, and records the exact row
count. For every selected race it filters rows with:

```text
historical_date < selected_race.scheduled_date
```

No row on or after the target date participates in feature computation.

Horse, jockey, trainer, and stud lookups first use trimmed exact values. A
normalized identity is accepted only when it resolves uniquely; ambiguity is an
error rather than a guessed match. Categorical values preserve the spelling
chosen for the participant so LightGBM can align them with the categories stored
in the fitted artifact.

Age comes from the horse's most recent historical row strictly before the race.
If any participant has no prior horse record or no valid age, prediction fails;
the engine does not fabricate an average.

The engine emits these 18 columns in exactly this order:

1. `Jinete_WinRate_Smoothed`
2. `Jinete_Carreras_Prev`
3. `Preparador_WinRate_Smoothed`
4. `Preparador_Carreras_Prev`
5. `Caballo_WinRate_Smoothed`
6. `Caballo_Carreras_Prev`
7. `Caballo_Puesto_Prom_Hist`
8. `Stud_WinRate_Smoothed`
9. `Duo_WinRate_Smoothed`
10. `Peso_Num`
11. `Distancia_Num`
12. `Edad_Num`
13. `Mandil_Num`
14. `Competidores_Carrera`
15. `Prob_Base_Lote`
16. `Jinete_Limpio`
17. `Prep_Limpio`
18. `Stud_Limpio`

Smoothing reproduces the training code: prior weight 5 for jockey, trainer, and
stud; prior weight 2 for horse and jockey-trainer pair; the artifact's stored
global win rate supplies the prior mean.

## 5. `RealLightGBMRaceModel`

Construction requires model path, dataset feature engine, and the pinned digest.
Loading performs these checks in order:

1. The model and dataset are regular files.
2. The model SHA-256 matches the pinned digest using constant-time comparison.
3. Installed LightGBM major version is 4.
4. Pickle deserialization succeeds.
5. The top-level object is a mapping with `model`, `feature_cols`,
   `categorical_cols`, and `global_win_rate`.
6. `feature_cols` exactly equals the approved 18-column contract.
7. Categorical columns exactly equal `Jinete_Limpio`, `Prep_Limpio`, and
   `Stud_Limpio`.
8. The estimator exposes `predict_proba` and reports 18 input features.

Any failure raises `RealModelArtifactError` with a user-safe explanation. The
original exception is retained as its cause for logs but is not rendered in the
dashboard.

`predict_race` builds a pandas DataFrame in the artifact's column order, casts
the three categorical columns to `category`, and obtains binary winner scores.
It rejects empty, negative, non-finite, or wrong-length output. Scores are
normalized jointly within the race and adjusted so the final sum is exactly
1.0. Top-N probabilities use the existing exact Plackett-Luce implementation.
Fair decimal odds are `1 / win_probability`.

Metadata identifies the model as `historical_lightgbm_v1`, the dataset row count
as 31,418, and the training period. It does not claim independent calibration or
issue wagering recommendations.

## 6. Dashboard Data Flow

`PredictionService` becomes real-model-only and receives a validated
`RealLightGBMRaceModel`. For the selected `RaceOption` and its read-only
`RaceParticipant` rows it:

1. Builds the current participant descriptors.
2. Requests leakage-safe 18-column feature rows.
3. Runs LightGBM inference.
4. Returns win probability, Top-3 probability, and fair decimal odds.

The Streamlit view lazily constructs and caches the service. A missing or corrupt
artifact shows:

```text
Error: Artefactos del modelo no encontrados o corruptos. Por favor, ejecute el
pipeline de entrenamiento.
```

The app stops the prediction calculation and never invokes
`BaselineRaceModel`. Successful output displays:

```text
Predicción generada por el modelo LightGBM entrenado con 31,418 registros
históricos (2024-2026)
```

The table contains Mandil, Caballo, Prob. Ganar, Prob. Placé (Top 3), and
Dividendo Justo.

## 7. Fire Test

Because the current ignored dashboard database has no registered races, the
fire test creates an ignored SQLite database under `var/ml/real-model/` with the
approved Derby race and seven participants. It uses the real local artifacts,
launches Streamlit headlessly, and exercises the same service used by the UI.
No synthetic model, fabricated history row, or committed database is allowed.

## 8. Testing

- Missing model and missing dataset fail closed.
- Wrong SHA-256 fails before pickle deserialization.
- Invalid artifact keys or feature order fail closed.
- Historical features exclude rows on and after the race date.
- Age uses the most recent prior horse record.
- Missing age/history rejects the entire prediction.
- Real probabilities are finite, positive, and sum exactly to 1.0.
- Fair odds equal the reciprocal of win probability.
- Dashboard service never instantiates the synthetic baseline.
- Existing 119 tests remain green.
- Ruff and Mypy remain clean.

## 9. Non-Goals

- Retraining or tuning the supplied model during dashboard startup.
- Claiming the model is calibrated or profitable.
- Committing CSV, pickle, SQLite, or generated predictions.
- Falling back to synthetic features or a synthetic model.
- Writing predictions back to the database.
