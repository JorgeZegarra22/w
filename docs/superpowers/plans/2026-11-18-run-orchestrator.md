# Run Orchestrator and Unit of Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the approved discovery-to-facts pipeline atomically and prove end-to-end idempotency against a local HTTP server and synthetic PDF.

**Architecture:** A Core `UnitOfWork` owns one SQLAlchemy connection and transaction. `RunOrchestrator` coordinates source registration, robots decisions, HTML discovery, downloads, blob storage, document/version registration, extraction, review routing, tasks, reports, metrics, and checkpoints; uniqueness constraints and fingerprints turn repeated work into reads rather than duplicate writes.

**Tech Stack:** Python 3.12, SQLAlchemy Core, HTTPX, pdfplumber, ReportLab, pytest-httpserver, Pytest, Ruff, Mypy.

**Spec:** `docs/architecture/entregable-1-architecture.md`, sections 5–14; sequence diagrams under `docs/architecture/diagrams/`.

## Global Constraints

- No UI, predictive model, real source data, OCR, PostgreSQL installation, or Tesseract.
- Database records for a failed pipeline are rolled back as one unit; an already verified immutable blob may remain recoverable outside the database.
- All IDs are application-generated ULID strings and all content identities use SHA-256.
- Policy evaluation precedes index and document fetches.
- The second run with unchanged content does not create duplicate publications, versions, documents, blobs, extraction runs, facts, evidence, reviews, or processing tasks.
- Every behavior is introduced through a failing test and the complete suite remains green.

---

### Task 1: Test dependency and transaction boundary

**Files:**

- Modify: `pyproject.toml`
- Create: `src/benter_peru/db/uow.py`
- Create: `tests/db/test_uow.py`

**Interfaces:**

- Produces: `UnitOfWork(engine)` context manager with active `connection`, `commit()`, and `rollback()`.
- Consumes: SQLAlchemy `Engine`, `Connection`, and root `Transaction`.

- [ ] Add `pytest-httpserver>=1.1,<2.0` to development dependencies and reinstall editable dependencies.
- [ ] Write one test proving normal context exit commits a source row and one test proving an exception rolls the insert back completely.
- [ ] Run `python -m pytest tests/db/test_uow.py -q` and observe the missing-module failure.
- [ ] Implement explicit connect/begin on entry, commit on clean exit, rollback on exceptional exit, connection closure, and guarded access outside the context.
- [ ] Re-run the focused tests until green.

### Task 2: Adapter trace fields required by orchestration

**Files:**

- Modify: `src/benter_peru/http/client.py`
- Modify: `src/benter_peru/policy.py`
- Modify: `src/benter_peru/extraction/models.py`
- Modify: `tests/http/test_client.py`
- Modify: `tests/test_policy.py`
- Modify: `tests/extraction/test_router.py`

**Interfaces:**

- Produces: response extension `benter_attempt_count`; `PolicyDecision.robots_sha256`; `TextEvidence.confidence` and `TextEvidence.requires_review`.
- Consumes: existing adapter outputs.

- [ ] Add failing assertions for HTTP attempt count, exact robots content SHA-256, and default extraction confidence/review fields.
- [ ] Run the three focused test modules and verify the new assertions fail for missing fields.
- [ ] Add the minimal immutable fields and set the response extension on successful responses.
- [ ] Re-run focused tests until green.

### Task 3: Deterministic discovery and identifiers

**Files:**

- Create: `src/benter_peru/ids.py`
- Create: `src/benter_peru/discovery.py`
- Create: `tests/test_ids.py`
- Create: `tests/test_discovery.py`

**Interfaces:**

- Produces: `new_ulid() -> str`; `SourceDefinition`; `DiscoveredDocument`; `HtmlDocumentDiscoverer.discover(html, base_url)`.
- Consumes: links explicitly marked with `data-document-type`, never remote filenames.

- [ ] Write failing tests proving ULIDs are 26 Crockford characters and unique, relative links become absolute, unmarked links are ignored, and link text is retained as context.
- [ ] Implement the minimal standard-library HTML parser and ULID encoder.
- [ ] Re-run focused tests until green.

### Task 4: End-to-end orchestrator

**Files:**

- Create: `src/benter_peru/orchestrator/__init__.py`
- Create: `src/benter_peru/orchestrator/models.py`
- Create: `src/benter_peru/orchestrator/run.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_run_orchestrator.py`

**Interfaces:**

- Produces: `RunOrchestrator.run(source_code, correlation_id) -> RunResult`.
- Consumes: `UnitOfWork`, source definitions, discoverer, PolicyGate, ResponsibleHttpClient, LocalBlobStore, ExtractionRouter, SQLAlchemy Core tables, and injected ULID/clock functions.

- [ ] Configure a local pytest-httpserver with permissive robots, one HTML index containing a typed document link, and one in-memory ReportLab PDF.
- [ ] Write the E2E test expecting one physical blob; one logical document/version/task/extraction; text facts, evidence, and review items; and one report/metric set after the first run.
- [ ] Run the same orchestrator with a second correlation ID and assert extraction was called once total, immutable entity counts do not increase, the second run reports deduplication, and all twenty schema tables remain valid.
- [ ] Write a rollback test using an extractor that raises after document registration and assert source/run/document/version/task rows are absent.
- [ ] Run the integration module and observe the missing-orchestrator failure.
- [ ] Implement source/crawl registration, policy snapshots, fetch attempts, publication/version/link upserts, blob/document/version upserts, task/extraction/fact/evidence/review persistence, report metrics, checkpoint update, and result reconstruction for repeated correlation IDs.
- [ ] Re-run integration tests until green.

### Task 5: Verification and review checkpoint

**Files:**

- Modify only files above when a demonstrated defect requires correction.

**Interfaces:**

- Produces: a committed Step 4 checkpoint preserved for explicit merge approval.
- Consumes: all prior persistence and adapter functionality.

- [ ] Run `python -m pytest -q` and the coverage command.
- [ ] Run `python -m ruff check .` and `python -m mypy src`.
- [ ] Run `git diff --check`, verify no protected artifacts are tracked, and inspect the staged file list.
- [ ] Commit with message `feat: orchestrate idempotent document runs` without merging or pushing.
