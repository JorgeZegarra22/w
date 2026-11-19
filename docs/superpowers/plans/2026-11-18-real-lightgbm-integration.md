# Real LightGBM Model Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the trusted historical LightGBM artifact into the read-only dashboard with leakage-safe features, exact race normalization, fair odds, and fail-fast artifact validation.

**Architecture:** A historical CSV feature engine owns the 18-column inference contract and strict date boundary. `RealLightGBMRaceModel` owns digest verification, artifact validation, LightGBM inference, race normalization, and Plackett-Luce place probabilities. The dashboard service composes both without a synthetic fallback.

**Tech Stack:** Python 3.12, pandas, NumPy, LightGBM 4.x, Streamlit, SQLAlchemy Core, Pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-11-18-real-lightgbm-integration-design.md`

## Global Constraints

- Model digest is `18c751b283a5af4461e5f9c16604e135bf56b00d0241f3f6c6c14e7d4537852f`.
- Dataset has 31,418 rows dated 2024-01-06 through 2026-11-15.
- Every historical feature uses rows with `Fecha < race_date`.
- Missing, altered, incompatible, ambiguous, or incomplete inputs fail closed.
- No dashboard code may instantiate or fall back to `BaselineRaceModel`.
- CSV, pickle, SQLite, and generated predictions stay ignored and uncommitted.

---

### Task 1: Artifact hygiene and dependency contract

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Create: `tests/ml/test_real_artifact_config.py`

**Interfaces:**
- Produces: ignored local paths and LightGBM runtime dependency.

- [ ] Write a failing test that asserts the default model/dataset paths and pinned digest constants.
- [ ] Run `python -m pytest tests/ml/test_real_artifact_config.py -q` and observe the missing symbols.
- [ ] Add `lightgbm>=4.6,<5.0`, explicit ignore rules, environment examples, and constants.
- [ ] Run the focused test and verify GREEN.
- [ ] Move the two heavy artifacts to `var/ml/real-model/` and verify `git check-ignore` accepts both.

### Task 2: Leakage-safe 18-column feature engine

**Files:**
- Create: `src/benter_peru/ml/real_features.py`
- Create: `tests/ml/test_real_features.py`

**Interfaces:**
- Produces: `RealRaceParticipant`, `LightGBMFeatureRow`, `HistoricalLightGBMFeatureEngine.for_race(...)`.
- Consumes: validated dataset CSV, race date/distance, participant names and physical data, artifact global win rate.

- [ ] Write synthetic-CSV tests for exact column order, smoothed counts/rates, and field-size features.
- [ ] Run the focused tests and confirm RED due to the missing module.
- [ ] Implement strict CSV/schema parsing and the minimum statistics needed for GREEN.
- [ ] Write a failing test proving rows on/after the target date are excluded and age comes from the latest prior row.
- [ ] Implement the strict `< race_date` filter and age resolution.
- [ ] Write a failing test for missing horse history and ambiguous normalized identities.
- [ ] Implement fail-closed identity and history validation.
- [ ] Run focused Pytest, Ruff, and Mypy checks.

### Task 3: Hash-pinned LightGBM loader and prediction

**Files:**
- Modify: `src/benter_peru/ml/models.py`
- Create: `tests/ml/test_real_model.py`

**Interfaces:**
- Produces: `RealLightGBMRaceModel.load(...)`, `RealModelArtifactError`, and real `RacePrediction`.
- Consumes: `HistoricalLightGBMFeatureEngine` and `LightGBMFeatureRow` mappings.

- [ ] Write failing tests for missing model, missing dataset, and wrong digest.
- [ ] Implement pre-deserialization file and constant-time digest validation.
- [ ] Write failing tests using a tiny locally trained LightGBM artifact for invalid keys, feature order, and runtime inference.
- [ ] Implement artifact/version/schema validation and DataFrame construction.
- [ ] Write a failing test for exact probability sum, Plackett-Luce Top-3, and finite fair odds.
- [ ] Implement prediction normalization and metadata while preserving the existing baseline API.
- [ ] Run focused Pytest, Ruff, and Mypy checks.

### Task 4: Real-only dashboard composition

**Files:**
- Modify: `src/benter_peru/ui/service.py`
- Modify: `src/benter_peru/ui/app.py`
- Modify: `tests/ui/test_service.py`
- Create: `tests/ui/test_app_real_model.py`

**Interfaces:**
- Produces: real-model `PredictionService`, fair-odds output, friendly fail-fast UI.
- Consumes: read-only `DashboardRepository`, real model paths, selected race and participants.

- [ ] Replace the service test with a failing injected-real-model contract test.
- [ ] Implement dependency-injected real service composition without baseline construction.
- [ ] Write failing UI-helper tests for missing/corrupt artifacts and the 31,418-row provenance note.
- [ ] Implement cached real service creation, friendly error handling, fair odds, and provenance display.
- [ ] Run focused dashboard tests, Ruff, and Mypy.

### Task 5: Integrate and refactor Sandbox scripts

**Files:**
- Create: `src/benter_peru/ml/entrenar_modelo.py`
- Create: `src/benter_peru/ml/predecir_derby.py`
- Create: `tests/ml/test_real_scripts.py`
- Remove after verified relocation: `hipicocvs/entrenar_modelo.py`, `hipicocvs/predecir_derby.py`

**Interfaces:**
- Produces: typed training entry point and Derby prediction entry point that reuse production contracts.

- [ ] Write failing import/argument tests for both modules.
- [ ] Refactor the training script to accept explicit paths and emit the versioned artifact mapping.
- [ ] Refactor the Derby script to call `RealLightGBMRaceModel`, not duplicate feature engineering.
- [ ] Run focused tests and static checks.
- [ ] Remove the empty Sandbox folder after every source and artifact has a verified destination.

### Task 6: Real artifact fire test and complete verification

**Files:**
- Create only ignored runtime files below: `var/ml/real-model/`
- Modify completion status only: this plan and its spec.

**Interfaces:**
- Exercises the same service and artifacts used by Streamlit.

- [ ] Verify the relocated model and dataset hashes and row/date range.
- [ ] Build an ignored Derby SQLite fixture with seven approved participants.
- [ ] Execute the real prediction service and capture seven win probabilities and fair odds.
- [ ] Launch `streamlit run src/benter_peru/ui/app.py` headlessly and confirm startup without exceptions.
- [ ] Run `python -m pytest -q`, `python -m ruff check .`, and `python -m mypy src`.
- [ ] Verify no CSV, pickle, SQLite, or generated prediction is tracked.
- [ ] Mark the spec and plan implemented, commit, and stop for review.
