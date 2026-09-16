import pytest
from httpx import AsyncClient, ASGITransport


def test_limiter_uses_redis_url_when_set(monkeypatch):
    """Limiter should use REDIS_URL from environment when available."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    import importlib
    import utils.config as config_module
    importlib.reload(config_module)
    import api.rate_limit as rate_limit_module
    importlib.reload(rate_limit_module)

    assert rate_limit_module.limiter._storage_uri == "redis://localhost:6379/0"


def test_limiter_falls_back_to_memory_when_no_redis(monkeypatch):
    """Limiter should fall back to in-memory when REDIS_URL is not set."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    import importlib
    import utils.config as config_module
    importlib.reload(config_module)
    import api.rate_limit as rate_limit_module
    importlib.reload(rate_limit_module)

    assert rate_limit_module.limiter._storage_uri is None
    assert rate_limit_module.limiter._in_memory_fallback_enabled is True


def _request_with_xff(value: str | None):
    from starlette.requests import Request

    headers = [] if value is None else [(b"x-forwarded-for", value.encode())]
    return Request({"type": "http", "headers": headers, "client": ("9.9.9.9", 1234)})


def test_client_ip_uses_last_forwarded_hop():
    """Only the hop our proxy appended is trusted; the first is client-controlled."""
    from api.rate_limit import client_ip

    assert client_ip(_request_with_xff("1.2.3.4, 10.0.0.1")) == "10.0.0.1"


def test_client_ip_falls_back_to_peer_without_forwarded_header():
    from api.rate_limit import client_ip

    assert client_ip(_request_with_xff(None)) == "9.9.9.9"


@pytest.mark.asyncio
async def test_rate_limited_endpoint_returns_429():
    """Rate-limited endpoints should return 429 after exceeding limit."""
    from api.main import app
    from db.crud import create_session
    from db.database import async_session
    from models.schemas import InterviewPlan

    plan = InterviewPlan(candidate_name="Rate Limit", extracted_skills=[], question_bank=[])
    async with async_session() as db:
        session = await create_session(db, user_id="test-user-id", candidate_name="Rate Limit", plan_json=plan.model_dump_json())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # /token is limited to 5/hour - send 6 requests
        for _ in range(6):
            response = await ac.get("/token", params={"session_id": session.id})

        # 6th request should be rate limited
        assert response.status_code == 429
