import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "aura.db"))
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
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


async def get_db():
    async with async_session() as session:
        yield session
