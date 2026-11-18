# Core Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the responsible HTTP, robots policy, content-addressed blob, and text-only PDF extraction adapters required before orchestration.

**Architecture:** Each adapter owns one external boundary and exposes typed immutable results. Time, sleep, randomness, and HTTP transport are injected so retry and rate-limit behavior is deterministic in tests; PDF extraction uses pdfplumber word coordinates and returns `requires_ocr=True` without invoking OCR when no text layer exists.

**Tech Stack:** Python 3.12, HTTPX, pdfplumber, ReportLab test fixtures, Pytest, Ruff, Mypy.

**Spec:** `docs/architecture/entregable-1-architecture.md`, sections 5.2–5.9 and 11–13.

## Global Constraints

- Do not implement `RunOrchestrator`, database repositories, source discovery, OCR, or live network tests.
- User-Agent is mandatory and identifiable; retries cover 429, 5xx, and HTTPX timeouts.
- Backoff is exponential with injected jitter and honors numeric `Retry-After` values.
- The blob root must resolve outside the repository and filenames derive only from validated SHA-256 values.
- A repeated blob hash never rewrites or consumes the supplied stream.
- PDF tests use synthetic in-memory documents; no real PDF enters Git.
- Every production behavior is preceded by a failing test and all checks pass before the phase commit.

---

### Task 1: Dependency boundary

**Files:**

- Modify: `pyproject.toml`

**Interfaces:**

- Produces: runtime imports `httpx` and `pdfplumber`; development-only import `reportlab`.
- Consumes: existing editable package configuration.

- [ ] Add `httpx>=0.28,<1.0` and `pdfplumber>=0.11,<1.0` to runtime dependencies, and `reportlab>=4.2,<5.0` to `dev`.
- [ ] Run `python -m pip install -e ".[dev]"` and verify each dependency imports.

### Task 2: Responsible HTTP client

**Files:**

- Create: `src/benter_peru/http/__init__.py`
- Create: `src/benter_peru/http/client.py`
- Create: `tests/http/__init__.py`
- Create: `tests/http/test_client.py`

**Interfaces:**

- Produces: `HttpClientConfig`, `ResponsibleHttpClient.fetch(url, headers=None) -> httpx.Response`, and `RetryExhaustedError`.
- Consumes: injected `httpx.Client`, `sleep(seconds)`, `monotonic()`, and `jitter() -> float`.

- [ ] Write tests proving a 500 followed by 200 makes exactly two transport attempts, uses the configured User-Agent, and sleeps the literal deterministic backoff.
- [ ] Write tests proving a timeout is retried, a final retryable response raises `RetryExhaustedError`, numeric `Retry-After` wins over backoff, and per-host requests respect the configured minimum interval.
- [ ] Run `python -m pytest tests/http/test_client.py -q` and observe the missing-module failure.
- [ ] Implement the minimal typed client with retry statuses `{429, 500, 501, 502, 503, 504, 505, 506, 507, 508, 510, 511}`, timeout retries, host pacing, and deterministic injected dependencies.
- [ ] Re-run the focused tests until green.

### Task 3: Robots policy gate

**Files:**

- Create: `src/benter_peru/policy.py`
- Create: `tests/test_policy.py`

**Interfaces:**

- Produces: immutable `PolicyDecision` and `PolicyGate.evaluate(url) -> PolicyDecision`.
- Consumes: `ResponsibleHttpClient.fetch`, configured User-Agent, and standard-library `urllib.robotparser`.

- [ ] Write tests using HTTPX `MockTransport` proving `Disallow` denies the matching URL, `Allow` permits another URL, `Crawl-delay` is returned, and a 404 robots response permits access without delay.
- [ ] Run `python -m pytest tests/test_policy.py -q` and observe the missing-module failure.
- [ ] Implement origin-safe robots URL construction, parsing, wildcard delay fallback, 401/403 fail-closed decisions, and unavailable-policy errors for other failed responses.
- [ ] Re-run the focused tests until green.

### Task 4: Content-addressed local blob store

**Files:**

- Create: `src/benter_peru/storage/__init__.py`
- Create: `src/benter_peru/storage/local.py`
- Create: `tests/storage/__init__.py`
- Create: `tests/storage/test_local.py`

**Interfaces:**

- Produces: immutable `StoredBlob` and `LocalBlobStore.put_if_absent(stream, sha256) -> StoredBlob`.
- Consumes: binary file-like streams and an external configured root.

- [ ] Write tests proving a first write creates exactly one hash-named file, a repeated hash returns `created=False` without consuming or changing the target, a mismatched digest raises, and a repository-internal root is rejected.
- [ ] Run `python -m pytest tests/storage/test_local.py -q` and observe the missing-module failure.
- [ ] Implement SHA-256 validation, streaming to a same-filesystem temporary file, digest verification, atomic no-overwrite publication, and relative `storage_key` output.
- [ ] Re-run the focused tests until green.

### Task 5: Text-only extraction router

**Files:**

- Create: `src/benter_peru/extraction/__init__.py`
- Create: `src/benter_peru/extraction/models.py`
- Create: `src/benter_peru/extraction/pdf_text.py`
- Create: `src/benter_peru/extraction/router.py`
- Create: `tests/extraction/__init__.py`
- Create: `tests/extraction/test_router.py`

**Interfaces:**

- Produces: `BoundingBox`, `TextEvidence`, `ExtractionBundle`, `TextPdfExtractor.extract(source)`, and `ExtractionRouter.extract(source)`.
- Consumes: a filesystem path or seekable binary stream accepted by `pdfplumber.open`.

- [ ] Write an in-memory ReportLab PDF test proving extracted evidence contains page `1`, expected words, and positive ordered `(x0, top, x1, bottom)` coordinates.
- [ ] Write a blank synthetic PDF test proving `requires_ocr=True`, method `text`, and an empty evidence tuple.
- [ ] Run `python -m pytest tests/extraction/test_router.py -q` and observe the missing-module failure.
- [ ] Implement text-layer detection through page characters and call `extract_words()` only on pages with characters; never import or invoke OCR software.
- [ ] Re-run the focused tests until green.

### Task 6: Phase verification

**Files:**

- Modify only files above when verification identifies a defect.

**Interfaces:**

- Produces: a committed Step 3 checkpoint ready for `RunOrchestrator` after approval.
- Consumes: all adapters and prior persistence code.

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m pytest --cov=benter_peru --cov-report=term-missing -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `python -m mypy src`.
- [ ] Verify `git diff --check` and that Git tracks no PDF, database, `.env`, or local blob.
- [ ] Commit with message `feat: add responsible core adapters` and preserve the branch for review.
