import os
import asyncio
import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("DATABASE_PATH", ":memory:")
os.environ.setdefault("WORKER_API_KEY", "test-worker-key")


class _TestUser:
    id = "test-user-id"
    email = "test@example.com"
    name = "Test User"
    role = "admin"
    avatar_url = None


TEST_USER = _TestUser()
AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables in the test DB once per session."""
    from db.database import engine, Base
    from db.models import User, InterviewSession  # noqa: F401

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop().run_until_complete(_init())
    yield


@pytest.fixture(autouse=True)
def _apply_auth_override():
    """Re-apply dependency overrides before every test (handles module reloads)."""
    from api.main import app
    from api.deps import get_current_user

    async def _override_get_current_user(request=None):
        return TEST_USER

    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield
    # Don't clear — let individual tests clear if they need to test unauthenticated access


@pytest.fixture
def auth_headers():
    return AUTH_HEADERS


@pytest.fixture
def worker_headers():
    return {"Authorization": "Bearer test-worker-key"}
