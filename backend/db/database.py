import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "aura.db"))
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Columns added to ``users`` after the original release, as
# (column name, column DDL) pairs. ``create_all`` never alters existing
# tables, so pre-existing databases get the new columns via ALTER TABLE here.
# Keep in sync with db.models.User.
_USER_COLUMNS_ADDED = [
    ("password_hash", "VARCHAR(255)"),
    ("email_verified", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("verification_token_hash", "VARCHAR(64)"),
    ("verification_token_expires_at", "DATETIME"),
    ("reset_token_hash", "VARCHAR(64)"),
    ("reset_token_expires_at", "DATETIME"),
]


async def _add_missing_user_columns(conn) -> None:
    result = await conn.execute(text("PRAGMA table_info(users)"))
    existing = {row[1] for row in result.fetchall()}
    for column_name, column_ddl in _USER_COLUMNS_ADDED:
        if column_name not in existing:
            await conn.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_ddl}"))


async def init_db():
    async with engine.begin() as conn:
        from db.models import User, InterviewSession  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_user_columns(conn)


async def get_db():
    async with async_session() as session:
        yield session
