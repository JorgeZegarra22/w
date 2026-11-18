"""Explicit transaction boundary for one pipeline execution."""

from types import TracebackType

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.base import Transaction


class UnitOfWork:
    """Own one database connection and transaction for an atomic operation."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._transaction: Transaction | None = None

    @property
    def connection(self) -> Connection:
        if self._connection is None:
            raise RuntimeError("UnitOfWork must be entered before using its connection")
        return self._connection

    def __enter__(self) -> "UnitOfWork":
        if self._connection is not None:
            raise RuntimeError("UnitOfWork cannot be entered more than once")
        self._connection = self._engine.connect()
        self._transaction = self._connection.begin()
        return self

    def commit(self) -> None:
        if self._transaction is None or not self._transaction.is_active:
            raise RuntimeError("UnitOfWork has no active transaction")
        self._transaction.commit()

    def rollback(self) -> None:
        if self._transaction is not None and self._transaction.is_active:
            self._transaction.rollback()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                if self._transaction is not None and self._transaction.is_active:
                    self._transaction.commit()
            else:
                self.rollback()
        finally:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._transaction = None
