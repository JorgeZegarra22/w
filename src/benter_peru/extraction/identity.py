"""Stable extractor identity used by idempotency and persistence."""

EXTRACTOR_NAME = "pdfplumber-hipico-text"
# Version 3.0 exposed non-linear date-word ordering in the real PDF. Keeping it
# immutable preserves the audit trail; 3.1 adds geometric date recovery.
EXTRACTOR_VERSION = "3.1"
