# Scaffolding and Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the Python project skeleton and a tested SQLite schema that implements the approved Entregable 1 ERD and remains portable to PostgreSQL.

**Architecture:** Use a `src` layout, SQLAlchemy Core metadata as the application-facing schema, and an explicit Alembic initial migration as the reproducible database history. SQLite engines enable foreign keys on every connection; uniqueness, state, range, and identity constraints live in the database rather than only in Python.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x Core, Alembic, Pytest, pytest-cov, Ruff, Mypy.

**Spec:** `docs/architecture/entregable-1-architecture.md` and `docs/architecture/diagrams/entregable-1-erd.puml`

## Global Constraints

- Implement only scaffolding and persistence; do not add HTTP, extraction, orchestration, OCR, or real source data.
- Keep PDF files, SQLite databases, local data, secrets, and `.superpowers/` outside Git.
- Use application-generated `CHAR(26)` identifiers and `CHAR(64)` SHA-256 values.
- Use portable SQLAlchemy types, named constraints, explicit indexes, string states with `CHECK`, and Alembic migrations.
- Activate SQLite foreign keys for every application and test connection.
- Tests use temporary SQLite databases only.

---

### Task 1: Project scaffolding and dependency contract

**Files:**

- Create: `.gitignore`
- Create: `.env.example`
- Create: `pyproject.toml`
- Create: `alembic.ini`
- Create: `src/benter_peru/__init__.py`
- Create: `src/benter_peru/db/__init__.py`
- Create: `migrations/README.md`
- Create: `migrations/script.py.mako`
- Create: `tests/__init__.py`

**Interfaces:**

- Produces: installable package `benter-peru`; Pytest discovers `tests/`; Alembic reads `DATABASE_URL` through `migrations/env.py` in Task 3.
- Consumes: no application code.

- [ ] **Step 1: Define the packaging and tool configuration**

Declare Python `>=3.12,<3.14`, runtime dependencies `SQLAlchemy>=2.0,<3.0` and `alembic>=1.14,<2.0`, and development dependencies `pytest`, `pytest-cov`, `ruff`, and `mypy`. Configure Pytest with `testpaths = ["tests"]`, strict markers, and `pythonpath = ["src"]`.

- [ ] **Step 2: Define repository exclusions**

Ignore `.env`, `.superpowers/`, `.venv/`, `var/`, Python caches, coverage output, `*.db`, `*.sqlite*`, `*.pdf`, and temporary files. Keep `.env.example` tracked.

- [ ] **Step 3: Install the project in editable development mode**

Run: `python -m pip install -e ".[dev]"`

Expected: installation succeeds and `python -m pytest --version`, `python -m alembic --version`, `python -m ruff --version`, and `python -m mypy --version` exit successfully.

### Task 2: RED — executable schema contract

**Files:**

- Create: `tests/db/test_schema.py`
- Create: `tests/db/test_constraints.py`

**Interfaces:**

- Consumes: wished-for `benter_peru.db.engine.create_database_engine`, `benter_peru.db.migrations.upgrade_database`, and `benter_peru.db.schema.metadata`.
- Produces: behavioral contract for table inventory, foreign-key enforcement, required indexes, and critical uniqueness constraints.

- [ ] **Step 1: Write the failing schema inventory test**

```python
EXPECTED_TABLES = {
    "source_registry", "source_policy_snapshots", "source_checkpoints",
    "crawl_runs", "fetch_attempts", "http_cache_entries", "publications",
    "publication_versions", "documents", "publication_document_links",
    "blob_objects", "document_versions", "extraction_runs",
    "extracted_facts", "fact_evidence", "review_items",
    "review_decisions", "processing_tasks", "run_reports", "run_metrics",
}

def test_initial_migration_creates_approved_schema(tmp_path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'schema.db'}")
    upgrade_database(engine)
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
```

The production change caught is omission or accidental renaming of an approved ERD table.

- [ ] **Step 2: Write failing behavior tests for database enforcement**

Use real SQLAlchemy connections and literal fixture values to prove:

- `PRAGMA foreign_keys` equals `1`.
- inserting a child with an unknown `source_id` raises `IntegrityError`.
- duplicate `blob_objects.sha256` raises `IntegrityError`.
- duplicate `processing_tasks.idempotency_key` raises `IntegrityError`.
- duplicate `(document_id, blob_sha256)` raises `IntegrityError`.
- duplicate `run_reports.crawl_run_id` raises `IntegrityError`.
- confidence outside `[0, 1]`, non-positive page numbers, and negative counters raise `IntegrityError`.

- [ ] **Step 3: Run RED verification**

Run: `python -m pytest tests/db -q`

Expected: collection fails because `benter_peru.db.engine`, `benter_peru.db.migrations`, and `benter_peru.db.schema` do not exist. This is the expected missing-feature failure.

### Task 3: GREEN — portable metadata, engine, and initial migration

**Files:**

- Create: `src/benter_peru/db/schema.py`
- Create: `src/benter_peru/db/engine.py`
- Create: `src/benter_peru/db/migrations.py`
- Create: `migrations/env.py`
- Create: `migrations/versions/20261118_0001_initial_schema.py`
- Modify: `src/benter_peru/db/__init__.py`

**Interfaces:**

- Produces: `metadata: MetaData`; `create_database_engine(database_url: str) -> Engine`; `upgrade_database(engine: Engine, revision: str = "head") -> None`.
- Consumes: SQLAlchemy 2.x and Alembic configuration from Task 1.

- [ ] **Step 1: Implement the SQLite engine boundary**

`create_database_engine` accepts portable SQLAlchemy URLs and, for SQLite connections, registers an event that executes `PRAGMA foreign_keys=ON`. It returns a SQLAlchemy `Engine` without creating tables implicitly.

- [ ] **Step 2: Implement all twenty ERD tables in Core metadata**

Define the exact approved columns and relationships. Add named unique constraints for every pair listed in architecture section 7.5, named foreign keys, portable check constraints, and these indexes:

- `ix_processing_tasks_status_available_at`
- `ix_document_versions_processing_status`
- `ix_review_items_status_created_at`
- `ix_crawl_runs_source_id_started_at`
- first/last seen indexes for publications and documents

- [ ] **Step 3: Implement the explicit Alembic revision**

The revision identifier is `20261118_0001`. `upgrade()` creates the twenty tables in dependency order and then the approved indexes. `downgrade()` drops them in reverse dependency order. It contains no SQLite-only SQL.

- [ ] **Step 4: Implement programmatic migration execution**

`upgrade_database` builds an Alembic `Config`, passes the existing SQLAlchemy connection through `config.attributes["connection"]`, and upgrades to the requested revision. `migrations/env.py` reuses that connection when present and otherwise reads `DATABASE_URL` or the safe local default.

- [ ] **Step 5: Run GREEN verification**

Run: `python -m pytest tests/db -q`

Expected: all persistence tests pass with no warnings.

- [ ] **Step 6: Refactor without changing behavior**

Extract repeated SQL types and constraint helpers only when it reduces duplication without hiding table definitions. Re-run: `python -m pytest tests/db -q`.

### Task 4: Full phase verification and versioning

**Files:**

- Modify only files from Tasks 1–3 when verification exposes a defect.

**Interfaces:**

- Consumes: the complete scaffolding and persistence phase.
- Produces: a reproducible checkpoint ready for adapter work after human approval.

- [ ] **Step 1: Verify from tests and static analysis**

Run:

```text
python -m pytest -q
python -m pytest --cov=benter_peru --cov-report=term-missing
python -m ruff check .
python -m mypy src
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

Use a temporary `DATABASE_URL` for the Alembic round trip. Expected: every command exits `0`, all tests pass, and the database reaches `head` after upgrade/downgrade/upgrade.

- [ ] **Step 2: Audit repository safety**

Verify `git status --short --ignored`, `git diff --check`, and `git ls-files "*.pdf" "*.db" "*.sqlite*"`. Expected: no PDF or database is tracked, `.superpowers/` is ignored, and no whitespace errors exist.

- [ ] **Step 3: Commit the verified phase**

Commit only scaffolding, migration, schema, tests, and this plan with message `feat: add portable persistence foundation`.
