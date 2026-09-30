"""SQLite connection helpers for the insurance database."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "insurance.db"


def get_connection(*, read_only: bool = False) -> sqlite3.Connection:
    """Open the application database with foreign keys enabled.

    Initialization uses the default writable mode. Future query paths can use
    ``read_only=True`` to open SQLite in read-only mode and enable
    ``query_only`` as a second guard against writes.
    """

    if not read_only:
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DATABASE_PATH)
    else:
        database_uri = f"file:{DATABASE_PATH.as_posix()}?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if read_only:
        connection.execute("PRAGMA query_only = ON")
    return connection


@contextmanager
def connection_scope(*, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    """Provide a connection that is closed when the caller exits the scope."""

    connection = get_connection(read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()
