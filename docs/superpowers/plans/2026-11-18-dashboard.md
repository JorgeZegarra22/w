# Read-only Streamlit Dashboard Implementation Plan

**Implementation status:** COMPLETED — 2026-11-18 (`119 passed`, Ruff and Mypy clean)

**Goal:** Present database totals, race participants, and on-demand synthetic predictions without allowing the dashboard to create, migrate, or modify any persistent data.

**Architecture:** A framework-free query module owns SQLite read-only connection creation, schema validation, and typed projections. A prediction service composes those projections with the existing `FeatureEngine` and `BaselineRaceModel`. The Streamlit entrypoint is a thin presentation layer using pandas only for display tables.

**Tech Stack:** Python 3.12, SQLAlchemy Core, SQLite URI read-only mode, pandas, Streamlit, Pytest, Ruff, Mypy.

## Global Constraints

- Open SQLite with `mode=ro`; never create the database implicitly.
- Never run Alembic or issue DDL/DML from dashboard code.
- Validate `horses`, `races`, and `race_entries` before any view query.
- Convert missing-file and stale-schema failures into the approved friendly message.
- Train the synthetic baseline only after the explicit **Calcular Pronóstico** action.
- Preserve the mandatory non-production, non-calibrated warning.

## Task 1: Dependencies and RED query tests

- [x] Add bounded `pandas` and `streamlit` runtime dependencies.
- [x] Write tests for missing database, stale schema, read-only enforcement, summary counts, meetings/races, and participant projection.
- [x] Run the focused tests and observe RED because the UI query package does not exist.

## Task 2: GREEN read-only query layer

- [x] Implement `DashboardDatabaseError` and the approved public error message.
- [x] Build an absolute SQLite URI using `file:` plus `mode=ro` and the driver's URI flag.
- [x] Validate required tables through SQLAlchemy inspection.
- [x] Implement typed summary, race, and participant queries.
- [x] Run focused tests and observe GREEN.

## Task 3: RED/GREEN prediction service

- [x] Test feature calculation and race-normalized win/Top-3 output from seeded history.
- [x] Implement the service using existing `FeatureEngine` and `BaselineRaceModel`.
- [x] Fit the deterministic 500-by-7 synthetic baseline in memory and return typed display rows.
- [x] Verify exact win conservation and Top-3 conservation.

## Task 4: Streamlit presentation

- [x] Add the Resumen, Carreras, and Predicciones sidebar views.
- [x] Use pandas DataFrames for participant and prediction tables.
- [x] Stop execution with `st.error` and `st.stop` on database validation failure.
- [x] Keep Streamlit imports out of the query/service modules.
- [x] Reuse the documented `BENTER_DATABASE_PATH` environment variable.

## Task 5: Verification and commit

- [x] Run focused dashboard tests.
- [x] Run the complete pytest suite.
- [x] Run Ruff and Mypy.
- [x] Start Streamlit headlessly, poll its health endpoint, then stop it.
- [x] Confirm repository hygiene, mark this plan completed, and commit only intended source, test, dependency, and documentation changes.
