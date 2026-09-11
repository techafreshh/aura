import pytest
from db.database import init_db


@pytest.mark.asyncio
async def test_init_db_no_drift_on_fresh_schema():
    missing = await init_db()
    assert missing == {}
