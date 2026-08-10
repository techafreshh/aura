import importlib
import pytest
import os
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from api.main import app
from models.schemas import InterviewPlan, FinalReport, SectionGrade
from db.database import async_session
from db.crud import create_session, update_session_report


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
    plan = InterviewPlan(candidate_name="Token Test", extracted_skills=[], question_bank=[])
    async with async_session() as db:
        session = await create_session(db, user_id="test-user-id", candidate_name="Token Test", plan_json=plan.model_dump_json())
    with patch.dict(os.environ, {"LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/token?session_id={session.id}")
        assert response.status_code == 500
        assert "LiveKit credentials are not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_token_success():
    plan = InterviewPlan(candidate_name="Token Success", extracted_skills=[], question_bank=[])
    async with async_session() as db:
        session = await create_session(db, user_id="test-user-id", candidate_name="Token Success", plan_json=plan.model_dump_json())
    with patch.dict(os.environ, {"LIVEKIT_API_KEY": "fake_key", "LIVEKIT_API_SECRET": "fake_secret"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/token?session_id={session.id}")
        assert response.status_code == 200
        assert "token" in response.json()
        assert isinstance(response.json()["token"], str)


@pytest.mark.asyncio
async def test_get_token_rejects_another_users_session():
    from api.deps import get_current_user

    class Candidate:
        id = "candidate-user-id"
        role = "candidate"

    plan = InterviewPlan(candidate_name="Private Room", extracted_skills=[], question_bank=[])
    async with async_session() as db:
        session = await create_session(db, user_id="another-user-id", candidate_name="Private Room", plan_json=plan.model_dump_json())

    saved = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: Candidate()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/token?session_id={session.id}")
        assert response.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = saved


@pytest.mark.asyncio
async def test_get_plan_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer test-token"}) as ac:
        response = await ac.get("/plan/nonexistent-session-id")
    assert response.status_code == 404
    assert "Interview plan not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_plan_success():
    mock_plan = InterviewPlan(
        candidate_name="Test Candidate",
        extracted_skills=["Python"],
        question_bank=["What is Python?"]
    )
    async with async_session() as db:
        session = await create_session(
            db,
            user_id="test-user-id",
            candidate_name="Test Candidate",
            plan_json=mock_plan.model_dump_json(),
        )
        session_id = session.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer test-token"}) as ac:
        response = await ac.get(f"/plan/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["plan"]["candidate_name"] == "Test Candidate"
    assert data["plan"]["extracted_skills"] == ["Python"]
    assert data["plan"]["question_bank"] == ["What is Python?"]
    assert data["user_id"] == "test-user-id"
    assert data["user_email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_plan_returns_user_context_for_admin():
    """GET /plan returns plan + user_id + user_email so the worker can attribute traces.

    When an admin queries another user's session, user_email must be the session
    owner's email, not the requesting admin's — so Langfuse trace attribution
    points at the candidate.
    """
    mock_plan = InterviewPlan(
        candidate_name="Admin Test",
        extracted_skills=["Python"],
        question_bank=["Q1"],
    )
    owner_id = "some-other-user-id"
    owner_email = "candidate@example.com"
    from db.database import async_session
    from db.models import User

    async with async_session() as db:
        session = await create_session(
            db,
            user_id=owner_id,
            candidate_name="Admin Test",
            plan_json=mock_plan.model_dump_json(),
        )
        session_id = session.id
        db.add(User(
            id=owner_id,
            email=owner_email,
            name="Candidate",
            provider="google",
            provider_id="candidate-provider-id",
            role="candidate",
        ))
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer test-token"}) as ac:
        response = await ac.get(f"/plan/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == owner_id
    assert data["user_email"] == owner_email
    assert data["plan"]["candidate_name"] == "Admin Test"


def test_agent_initialization():
    """Verify that the agent can be imported and initialized without errors."""
    from agent.parser import agent
    assert agent is not None
    system_prompts = "".join(agent._system_prompts)
    assert "technical recruiter" in system_prompts


def test_cors_production_requires_domain(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DOMAIN", raising=False)
    # utils.config is the single source of truth for ENVIRONMENT — reload it
    # so the CORS branch in api.main sees the production value.
    import utils.config as config_module
    importlib.reload(config_module)
    import api.main as main_module
    with pytest.raises(RuntimeError, match="DOMAIN"):
        importlib.reload(main_module)


def test_cors_production_uses_domain(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DOMAIN", "https://example.com")
    import utils.config as config_module
    importlib.reload(config_module)
    import api.main as main_module
    importlib.reload(main_module)


@pytest.mark.asyncio
async def test_transcript_rejects_invalid_payload():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/transcript/test-session", json={"invalid": "payload"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_report_stream_returns_report():
    mock_plan = InterviewPlan(
        candidate_name="Test User",
        extracted_skills=["Python"],
        question_bank=["Q1"]
    )
    mock_report = FinalReport(
        candidate_name="Test User",
        overall_score=75,
        section_grades=[SectionGrade(section_name="Technical", score=8, comments="Good technical skills")],
        strengths=["Python", "Problem solving"],
        weaknesses=["Communication"],
        recommendation="Hire",
        summary="Strong technical candidate."
    )
    async with async_session() as db:
        session = await create_session(
            db,
            user_id="test-user-id",
            candidate_name="Test User",
            plan_json=mock_plan.model_dump_json(),
        )
        await update_session_report(db, session.id, mock_report.model_dump_json())
        session_id = session.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/report-stream/{session_id}")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "Test User" in response.text
