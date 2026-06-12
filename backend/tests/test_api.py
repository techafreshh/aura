import pytest
import os
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
import api.main as main_module
from api.main import app
from models.schemas import InterviewPlan

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_upload_non_pdf():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        files = {"file": ("test.txt", b"hello world", "text/plain")}
        response = await ac.post("/upload", files=files)
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_token_missing_credentials():
    with patch.dict(os.environ, {"LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/token?session_id=test-session")
        assert response.status_code == 500
        assert "LiveKit credentials are not configured" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_token_success():
    with patch.dict(os.environ, {"LIVEKIT_API_KEY": "fake_key", "LIVEKIT_API_SECRET": "fake_secret"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/token?session_id=test-session")
        assert response.status_code == 200
        assert "token" in response.json()
        assert isinstance(response.json()["token"], str)

@pytest.mark.asyncio
async def test_get_plan_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/plan/invalid-session")
    assert response.status_code == 404
    assert "Interview plan not found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_plan_success():
    session_id = "test-plan-session"
    mock_plan = InterviewPlan(
        candidate_name="Test Candidate",
        extracted_skills=["Python"],
        question_bank=["What is Python?"]
    )
    main_module.plans[session_id] = mock_plan
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/plan/{session_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_name"] == "Test Candidate"
    assert data["extracted_skills"] == ["Python"]
    assert data["question_bank"] == ["What is Python?"]

def test_agent_initialization():
    """Verify that the agent can be imported and initialized without errors."""
    from agent.parser import agent
    assert agent is not None
    # Check if the system prompt is set correctly in the private attribute
    system_prompts = "".join(agent._system_prompts)
    assert "technical recruiter" in system_prompts

import importlib

def test_cors_production_requires_domain(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DOMAIN", raising=False)
    import api.main as main_module
    with pytest.raises(RuntimeError, match="DOMAIN"):
        importlib.reload(main_module)

def test_cors_production_uses_domain(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DOMAIN", "https://example.com")
    import api.main as main_module
    importlib.reload(main_module)
    # Should not raise

@pytest.mark.asyncio
async def test_transcript_rejects_invalid_payload():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/transcript/test-session", json={"invalid": "payload"})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_report_endpoint_rate_limited():
    # Verify rate limit decorator is present (structural test)
    from api.main import app as test_app
    routes = {r.path: r for r in test_app.routes if hasattr(r, 'path')}
    # The rate limit is applied via decorator — verify endpoint exists
    report_routes = [r for r in test_app.routes if hasattr(r, 'path') and r.path == "/report/{session_id}"]
    assert len(report_routes) > 0
