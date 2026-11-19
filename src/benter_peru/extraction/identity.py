"""Stable extractor identity used by idempotency and persistence."""

EXTRACTOR_NAME = "pdfplumber-hipico-text"
# Version 3.1 remains immutable in the audit trail. Version 4.0 emits every
# complete race on every text page and includes race_number in entry payloads.
EXTRACTOR_VERSION = "4.0"
