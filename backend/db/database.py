import logging
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

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


async def init_db() -> dict[str, list[str]]:
    async with engine.begin() as conn:
        from db.models import User, OAuthIdentity, InterviewSession  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
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
        logger.error(
            "Database schema drift detected — missing columns: %s. "
            "For dev, delete %s and restart to recreate the schema; "
            "for prod, apply a manual ALTER TABLE matching db/models.py.",
            details,
            DB_PATH,
        )
    return missing


async def get_db():
    async with async_session() as session:
        yield session
