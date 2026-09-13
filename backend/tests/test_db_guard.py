import pytest
from db.database import init_db, engine


@pytest.mark.asyncio
async def test_init_db_no_drift_on_fresh_schema():
    missing = await init_db()
    assert missing == {}


@pytest.mark.asyncio
async def test_init_db_drift_raises_in_production_logs_in_dev(monkeypatch):
    """Simulate a stale schema by renaming a column the models expect.

    Production must fail loudly at startup; development must keep serving
    (log-only) so a stale local DB stays usable.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users RENAME COLUMN avatar_url TO avatar_url_stale"))
    try:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(RuntimeError, match="schema drift"):
            await init_db()

        monkeypatch.setenv("ENVIRONMENT", "development")
        missing = await init_db()
        assert missing == {"users": ["avatar_url"]}
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE users RENAME COLUMN avatar_url_stale TO avatar_url"))
