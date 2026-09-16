"""Tests for the Alembic migration chain against a fresh database.

The app's startup path runs ``alembic upgrade head`` on a file-based SQLite
database. These tests run the same migrations against a throwaway database
and assert the resulting schema matches the SQLAlchemy models — this guards
against migrations drifting from ``db/models.py`` (e.g. a new model table
being added without a corresponding migration).
"""

from pathlib import Path

import pytest

import db.database as db_database
from db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def migrated_db_path(tmp_path, monkeypatch):
    """Run ``alembic upgrade head`` against a throwaway SQLite file."""
    from alembic import command
    from alembic.config import Config

    db_path = str(tmp_path / "migration-test.db")
    # migrations/env.py resolves the target URL from db.database.DB_PATH at
    # migration time, so point that attribute at the throwaway file (restored
    # automatically after the test). The async engine used by the rest of the
    # test session stays on :memory: and is unaffected.
    monkeypatch.setattr(db_database, "DB_PATH", db_path)

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    return db_path


def _read_tables(db_path: str) -> set[str]:
    conn = __import__("sqlite3").connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_upgrade_head_creates_all_model_tables(migrated_db_path):
    actual = _read_tables(migrated_db_path)

    for table in Base.metadata.tables:
        assert table in actual, f"table {table!r} missing after `alembic upgrade head`"


def test_upgrade_head_matches_model_columns(migrated_db_path):
    """Every model column exists in the migrated schema (order-insensitive)."""
    import sqlite3

    conn = sqlite3.connect(migrated_db_path)
    try:
        for table in Base.metadata.tables.values():
            actual_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table.name})")}
            missing = set(table.columns.keys()) - actual_cols
            assert not missing, f"table {table.name} is missing columns after migration: {missing}"
    finally:
        conn.close()


def test_upgrade_head_is_idempotent(migrated_db_path):
    """Re-running upgrade on an up-to-date DB is a no-op, not an error."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")  # must not raise

    assert "oauth_identities" in _read_tables(migrated_db_path)