import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Make the backend package root importable regardless of the caller's cwd
# (uvicorn lifespan, CLI from repo root, etc.), then reuse the exact same
# database URL resolution as db/database.py so migrations always target the
# same database the app reads and writes — the SQLite file by default, or the
# server-backed database named by DATABASE_URL.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import database as db_database  # noqa: E402
from db.models import Base  # noqa: E402

target_metadata = Base.metadata


def _target_url() -> tuple[str, bool]:
    """Resolve the migration target URL at invocation time.

    Reads ``db.database``'s *current* attribute values instead of import-time
    snapshots: tests monkeypatch ``DB_PATH`` onto a throwaway file per test,
    and the startup path may run in a process whose env differs from the CLI
    that imported this module. Returns ``(sqlalchemy_url, is_sqlite)``.
    """
    url = db_database.resolve_db_url(db_database.DATABASE_URL, db_database.DB_PATH)
    return url, db_database.is_sqlite_url(url)


def _sync_sqlite_url(url: str) -> str:
    """Swap the async driver for Alembic's synchronous engine."""
    sync_url = url.replace("+aiosqlite", "", 1)
    if sync_url == "sqlite:///:memory:":
        sync_url = "sqlite://"  # per-connection :memory: is useless to Alembic
    return sync_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url, is_sqlite = _target_url()
    if is_sqlite:
        url = _sync_sqlite_url(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    SQLite goes through a synchronous engine. Server-backed URLs
    (``DATABASE_URL``, e.g. Postgres) go through the app's async driver via
    ``create_async_engine``, matching how the application itself connects —
    no second DBAPI needs to be installed.
    """
    url, is_sqlite = _target_url()

    if is_sqlite:
        connectable = create_engine(_sync_sqlite_url(url), poolclass=pool.NullPool)
        with connectable.connect() as connection:
            _run_migrations(connection)
        connectable.dispose()
    else:
        import asyncio

        from sqlalchemy.ext.asyncio import create_async_engine

        async def _async_run() -> None:
            engine = create_async_engine(url, poolclass=pool.NullPool)
            async with engine.connect() as connection:
                await connection.run_sync(_run_migrations)
            await engine.dispose()

        asyncio.run(_async_run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
