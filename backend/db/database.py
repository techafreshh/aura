import logging
import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from utils.config import get_environment

logger = logging.getLogger("database")

DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "aura.db"))
if DB_PATH != ":memory:":
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

if DB_PATH == ":memory:":
    # Share a single connection so all sessions see the same in-memory DB.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _find_missing_columns(sync_conn) -> dict[str, list[str]]:
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    missing: dict[str, list[str]] = {}
    for table in Base.metadata.tables.values():
        if not inspector.has_table(table.name):
            missing[table.name] = ["<missing table>"]
            continue
        actual = {col["name"] for col in inspector.get_columns(table.name)}
        diff = set(table.columns.keys()) - actual
        if diff:
            missing[table.name] = sorted(diff)
    return missing


# Columns added to ``users`` after the original release, as
# (column name, column DDL) pairs. Kept in sync with db.models.User and with
# the ``add_email_password_auth_columns`` Alembic migration. New databases get
# them through Alembic; pre-Alembic databases get them via ALTER TABLE in
# ``init_db`` (and in the startup auto-heal before stamping).
_USER_COLUMNS_ADDED = [
    ("password_hash", "VARCHAR(255)"),
    ("email_verified", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("verification_token_hash", "VARCHAR(64)"),
    ("verification_token_expires_at", "DATETIME"),
    ("reset_token_hash", "VARCHAR(64)"),
    ("reset_token_expires_at", "DATETIME"),
]


def _missing_user_columns(existing: set[str]) -> list[tuple[str, str]]:
    return [(name, ddl) for name, ddl in _USER_COLUMNS_ADDED if name not in existing]


async def _add_missing_user_columns(conn) -> None:
    result = await conn.execute(text("PRAGMA table_info(users)"))
    existing = {row[1] for row in result.fetchall()}
    for column_name, column_ddl in _missing_user_columns(existing):
        await conn.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_ddl}"))


def _add_missing_user_columns_sqlite(conn) -> None:
    """Sync variant used by the pre-Alembic auto-heal in ``api.main``.

    Raw ``sqlite3`` connection; callers commit. Brings a legacy ``users`` table
    up to the current model so the stamp-time drift check passes instead of
    rejecting the database.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    for column_name, column_ddl in _missing_user_columns(existing):
        conn.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_ddl}")


async def init_db() -> dict[str, list[str]]:
    async with engine.begin() as conn:
        from db.models import User, OAuthIdentity, InterviewSession, InterviewInvite  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        # Safety net for databases predating the ALTER-based migrations, and
        # for tests that exercise init_db directly without running Alembic.
        await _add_missing_user_columns(conn)
        # Backfill identities for databases created before multi-provider login.
        await conn.execute(text("""
            INSERT OR IGNORE INTO oauth_identities
                (id, user_id, provider, provider_id, email, created_at)
            SELECT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                   substr(lower(hex(randomblob(2))), 2) || '-' ||
                   substr('89ab', abs(random()) % 4 + 1, 1) ||
                   substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
                   id, provider, provider_id, lower(trim(email)), created_at
            FROM users
            WHERE provider IS NOT NULL AND provider_id IS NOT NULL
        """))

    async with engine.connect() as conn:
        missing = await conn.run_sync(_find_missing_columns)

    if missing:
        details = "; ".join(f"{table}: {', '.join(cols)}" for table, cols in missing.items())
        message = (
            f"Database schema drift detected — missing columns: {details}. "
            f"For dev, delete {DB_PATH} and restart to recreate the schema; "
            "for prod, apply a manual ALTER TABLE matching db/models.py."
        )
        # In production a drifted schema would 500 on every request with an
        # opaque "no such column"; failing at startup is the louder, earlier
        # failure. Development keeps serving so a stale local DB stays usable.
        if get_environment() == "production":
            raise RuntimeError(message)
        logger.error(message)
    return missing


async def get_db():
    async with async_session() as session:
        yield session
