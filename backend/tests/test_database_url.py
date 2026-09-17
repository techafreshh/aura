"""DATABASE_URL resolution — Postgres opt-in without touching SQLite defaults.

These tests are pure functions + the module constants; they never open a
connection, so no Postgres server is needed (the suite stays on the
in-memory SQLite engine, per conftest).
"""

import os

from db.database import DB_URL, DATABASE_URL, IS_SQLITE, is_sqlite_url, resolve_db_url


def test_unset_url_falls_back_to_sqlite_file():
    # Absolute path yields four slashes: scheme separator + path separator.
    assert resolve_db_url("", "/app/data/aura.db") == "sqlite+aiosqlite:////app/data/aura.db"


def test_unset_url_with_memory_path():
    assert resolve_db_url("", ":memory:") == "sqlite+aiosqlite:///:memory:"


def test_explicit_url_wins_verbatim():
    url = "postgresql+asyncpg://aura_user:pw@postgres:5432/aura"
    assert resolve_db_url(url, ":memory:") == url
    assert resolve_db_url(url, "/app/data/aura.db") == url


def test_is_sqlite_url():
    assert is_sqlite_url("sqlite+aiosqlite:///:memory:")
    assert is_sqlite_url("sqlite+aiosqlite:////app/data/aura.db")
    assert not is_sqlite_url("postgresql+asyncpg://aura_user:pw@postgres:5432/aura")


def test_module_targets_in_memory_sqlite_under_pytest():
    # conftest pins DATABASE_PATH=":memory:" and pops DATABASE_URL, so the
    # module the app and tests import must resolve to in-memory SQLite.
    assert DATABASE_URL == os.environ.get("DATABASE_URL", "").strip() == ""
    assert IS_SQLITE is True
    assert DB_URL == "sqlite+aiosqlite:///:memory:"
