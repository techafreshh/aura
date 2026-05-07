import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app
import io

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

def test_agent_initialization():
    """Verify that the agent can be imported and initialized without errors."""
    from agent.parser import agent
    assert agent is not None
    # Check if the system prompt is set correctly in the private attribute
    system_prompts = "".join(agent._system_prompts)
    assert "technical recruiter" in system_prompts
