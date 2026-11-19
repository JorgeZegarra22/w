# Estudie su Polla Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence-backed journalist picks and a fail-soft local daily pipeline.

**Architecture:** A document-type router emits `journalist_pick` facts; a transactional resolver materializes them into an idempotent table; read-only dashboard projections render labels; a local script composes collection, resolution, and prediction.

**Tech Stack:** Python 3.12, pdfplumber, SQLAlchemy Core, Alembic, Streamlit, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-estudie-polla-automation.md`

## Global Constraints

- No OCR or inferred identities.
- Missing magazine is fail-soft; discovered invalid magazine is fail-closed.
- Every pick retains document, fact, page, bbox, confidence, and raw text lineage.
- SQLite, model, dataset, PDFs, and generated reports remain local.

---

### Task 1: Deterministic magazine extractor and routing

**Files:** Create `src/benter_peru/extraction/estudie_polla.py`; modify router, identity, orchestrator; test `tests/extraction/test_estudie_polla.py` and router.

**Interfaces:** Produces `EstudiePollaExtractor.extract(source) -> ExtractionBundle` and document-type routing.

- [x] Generate clear, ambiguous, corrupt, and blank synthetic PDFs in failing tests.
- [x] Confirm RED from the missing module.
- [x] Implement marker validation, row extraction, evidence, and review facts.
- [x] Add a failing router test proving program and magazine paths are distinct.
- [x] Pass document type through local/network orchestration and processing fingerprints.
- [x] Run focused tests and static checks.

### Task 2: Migration and transactional materializer

**Files:** Create migration `20261118_0004`, modify schema, create `entities/journalist_picks.py`, add DB and resolver tests.

**Interfaces:** Produces `JournalistPickResolver.resolve_sha(sha256) -> JournalistPickReport`.

- [x] Write failing schema, constraint, idempotency, and review-preservation tests.
- [x] Implement the table and migration with portable constraints.
- [x] Implement strict JSON validation and UnitOfWork materialization.
- [x] Run focused tests and static checks.

### Task 3: Read-only dashboard projection

**Files:** Modify `ui/queries.py`, `ui/service.py`, and `ui/app.py`; add UI query/service tests.

**Interfaces:** Produces `DashboardRepository.journalist_picks_for_race(...)` and per-runner display labels.

- [x] Write failing tests for confirmed, review, and absent labels.
- [x] Implement read-only queries and deterministic reconciliation.
- [x] Add the column to Predictions and Strategy views.
- [x] Run focused tests and static checks.

### Task 4: Local daily pipeline

**Files:** Create `scripts/daily_pipeline.py`, `docs/operations/daily-pipeline.md`, and automation tests; modify CLI discovery types.

**Interfaces:** Produces `DailyPipeline.run(race_date) -> DailyPipelineReport` and a JSON script entry point.

- [x] Write failing tests for magazine absent, present, and discovered-invalid.
- [x] Implement dependency-injected orchestration policy.
- [x] Wire the production script to collection, resolvers, and date-scoped prediction.
- [x] Document Windows Task Scheduler and cron invocation.
- [x] Run focused tests and static checks.

### Task 5: Verification and handoff

- [x] Run all Pytest tests, including HTTP E2E tests outside the socket sandbox.
- [x] Run Ruff and Mypy for `src` and `scripts`.
- [x] Run synthetic fire tests and capture confirmed/review/absent outputs.
- [x] Mark spec and plan implemented, commit the branch, and stop for review.
