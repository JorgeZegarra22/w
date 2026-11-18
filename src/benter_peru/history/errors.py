"""Stable errors for strict history imports."""


class HistoryImportError(ValueError):
    """A CSV error with a precise row and field location."""

    def __init__(self, row_number: int | None, field: str, reason: str) -> None:
        self.row_number = row_number
        self.field = field
        self.reason = reason
        location = f"row {row_number}, " if row_number is not None else ""
        super().__init__(f"{location}{field}: {reason}")

