"""Database engine construction with SQLite safety settings."""

import sqlite3

from sqlalchemy import Engine, create_engine, event


def create_database_engine(database_url: str) -> Engine:
    """Create an engine and enforce SQLite foreign keys on every connection."""
    engine = create_engine(database_url)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(
            dbapi_connection: sqlite3.Connection, _connection_record: object
        ) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine
