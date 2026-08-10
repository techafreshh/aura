import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app
from api.deps import get_current_user
from models.schemas import InterviewPlan, FinalReport, SectionGrade
from db.database import async_session
from db.crud import create_session, update_session_report, upsert_user
from db.models import User


def _admin_user():
    return User(
        id="admin-user-id",
        email="admin@example.com",
        name="Admin",
        provider="google",
        provider_id="admin-provider",
        role="admin",
    )


def _candidate_user():
    return User(
        id="candidate-user-id",
        email="candidate@example.com",
        name="Candidate",
        provider="google",
        provider_id="candidate-provider",
        role="candidate",
    )


@pytest.fixture
def admin_user():
    return _admin_user()


@pytest.fixture
def candidate_user():
    return _candidate_user()


@pytest.fixture
def auth_as_admin():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    yield TEST_USER
    # Restore to test default
    from tests.conftest import TEST_USER as DEFAULT

    async def _restore():
        return DEFAULT

    app.dependency_overrides[get_current_user] = _restore


@pytest.fixture
def auth_as_candidate():
    from tests.conftest import TEST_USER

    async def _override():
        return _candidate_user()

    app.dependency_overrides[get_current_user] = _override
    yield TEST_USER
    from tests.conftest import TEST_USER as DEFAULT

    async def _restore():
        return DEFAULT

    app.dependency_overrides[get_current_user] = _restore


async def _seed_other_user_with_session(other_email: str = "other-candidate@example.com", name: str = "Other Candidate"):
    """Create a separate user with one session for cross-user access tests."""
    async with async_session() as db:
        user = await upsert_user(
            db,
            email=other_email,
            name=name,
            provider="google",
            provider_id=f"provider-{other_email}",
        )
        plan = InterviewPlan(
            candidate_name=name,
            extracted_skills=["Go"],
            question_bank=["Q1"],
        )
        session = await create_session(
            db,
            user_id=user.id,
            candidate_name=name,
            plan_json=plan.model_dump_json(),
        )
        return user, session


@pytest.mark.asyncio
async def test_admin_list_sessions_requires_admin():
    from tests.conftest import TEST_USER

    async def _override():
        return _candidate_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/admin/sessions")
        assert response.status_code == 403
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_list_sessions_returns_all():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        # Seed two sessions owned by other users
        _, s1 = await _seed_other_user_with_session("user1@example.com", "User One")
        _, s2 = await _seed_other_user_with_session("user2@example.com", "User Two")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/admin/sessions")
        assert response.status_code == 200
        data = response.json()
        ids = {item["session_id"] for item in data}
        assert s1.id in ids
        assert s2.id in ids
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_list_sessions_status_filter():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        _, session = await _seed_other_user_with_session("filter@example.com", "Filter Candidate")
        mock_report = FinalReport(
            candidate_name="Filter Candidate",
            overall_score=80,
            section_grades=[SectionGrade(section_name="Technical", score=8, comments="Good")],
            strengths=["x"],
            weaknesses=["y"],
            recommendation="Hire",
            summary="Solid.",
        )
        async with async_session() as db:
            await update_session_report(db, session.id, mock_report.model_dump_json())

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/admin/sessions?status=completed")
        assert response.status_code == 200
        data = response.json()
        # The completed session should be present
        match = [s for s in data if s["session_id"] == session.id]
        assert len(match) == 1
        assert match[0]["status"] == "completed"
        assert match[0]["overall_score"] == 80
        assert match[0]["recommendation"] == "Hire"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/admin/sessions?status=in_progress")
        assert response.status_code == 200
        data = response.json()
        # Should not include the completed session
        ids = {item["session_id"] for item in data}
        assert session.id not in ids
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_list_sessions_invalid_status():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/admin/sessions?status=garbage")
        assert response.status_code == 422
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_sessions_mine_returns_only_users_own_sessions():
    from tests.conftest import TEST_USER

    # Pretend the default TEST_USER owns the seeded session
    mock_plan = InterviewPlan(
        candidate_name="Mine User",
        extracted_skills=["Python"],
        question_bank=["Q1"],
    )
    async with async_session() as db:
        mine = await create_session(
            db,
            user_id=TEST_USER.id,
            candidate_name="Mine User",
            plan_json=mock_plan.model_dump_json(),
        )
    # And another user has a session
    _, theirs = await _seed_other_user_with_session("other@example.com", "Other User")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/sessions/mine")
    assert response.status_code == 200
    data = response.json()
    ids = {item["session_id"] for item in data}
    assert mine.id in ids
    assert theirs.id not in ids


@pytest.mark.asyncio
async def test_sessions_mine_requires_auth():
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/sessions/mine")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.update(saved)


@pytest.mark.asyncio
async def test_candidate_session_detail_returns_report_and_transcript():
    from tests.conftest import TEST_USER
    import json

    plan = InterviewPlan(candidate_name="Mine Detail", extracted_skills=["Python"], question_bank=["Q1"])
    report = FinalReport(
        candidate_name="Mine Detail", overall_score=82,
        section_grades=[SectionGrade(section_name="Technical", score=8, comments="Good")],
        strengths=["Python"], weaknesses=[], recommendation="Hire", summary="Good interview.",
    )
    async with async_session() as db:
        session = await create_session(db, user_id=TEST_USER.id, candidate_name="Mine Detail", plan_json=plan.model_dump_json())
        await update_session_report(db, session.id, report.model_dump_json())
        stored = await db.get(type(session), session.id)
        stored.transcript_json = json.dumps([{"speaker": "Candidate", "text": "Hello", "timestamp_s": 1.2}])
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/sessions/{session.id}/detail")
    assert response.status_code == 200
    assert response.json()["report"]["overall_score"] == 82
    assert response.json()["transcript"][0]["text"] == "Hello"


@pytest.mark.asyncio
async def test_candidate_session_detail_rejects_other_users_session():
    from tests.conftest import TEST_USER

    async def _override():
        return _candidate_user()

    app.dependency_overrides[get_current_user] = _override
    _, session = await _seed_other_user_with_session("private@example.com", "Private")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/sessions/{session.id}/detail")
        assert response.status_code == 403
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_get_session_detail():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        owner, session = await _seed_other_user_with_session("detail@example.com", "Detail Candidate")
        mock_report = FinalReport(
            candidate_name="Detail Candidate",
            overall_score=72,
            section_grades=[SectionGrade(section_name="Behavioral", score=7, comments="Solid")],
            strengths=["Communicates well"],
            weaknesses=["Could be more concise"],
            recommendation="Hold",
            summary="Good communicator, average depth.",
        )
        async with async_session() as db:
            await update_session_report(db, session.id, mock_report.model_dump_json())

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/admin/sessions/{session.id}/detail")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session.id
        assert data["candidate_name"] == "Detail Candidate"
        assert data["user_email"] == owner.email
        assert data["status"] == "completed"
        assert data["plan"]["candidate_name"] == "Detail Candidate"
        assert data["report"]["overall_score"] == 72
        assert data["report"]["recommendation"] == "Hold"
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_get_session_detail_requires_admin():
    from tests.conftest import TEST_USER

    async def _override():
        return _candidate_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        _, session = await _seed_other_user_with_session("admin-required@example.com", "Admin Required")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/admin/sessions/{session.id}/detail")
        assert response.status_code == 403
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_get_session_detail_404():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/admin/sessions/does-not-exist/detail")
        assert response.status_code == 404
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_get_session_report_uses_db():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        _, session = await _seed_other_user_with_session("report@example.com", "Report Candidate")
        mock_report = FinalReport(
            candidate_name="Report Candidate",
            overall_score=88,
            section_grades=[SectionGrade(section_name="Technical", score=9, comments="Excellent")],
            strengths=["Strong problem solving"],
            weaknesses=[],
            recommendation="Strong Hire",
            summary="Top candidate.",
        )
        async with async_session() as db:
            await update_session_report(db, session.id, mock_report.model_dump_json())

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/admin/sessions/{session.id}/report")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_score"] == 88
        assert data["recommendation"] == "Strong Hire"
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_get_session_report_404_when_no_report():
    from tests.conftest import TEST_USER

    async def _override():
        return _admin_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        _, session = await _seed_other_user_with_session("noreport@example.com", "No Report Candidate")
        # No report saved. With MinIO returning None, we expect 404.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/admin/sessions/{session.id}/report")
        # If MinIO is unavailable, get_artifact returns None, so 404. If MinIO
        # is reachable but missing the file, get_artifact still returns None.
        assert response.status_code == 404
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore


@pytest.mark.asyncio
async def test_admin_get_session_report_requires_admin():
    from tests.conftest import TEST_USER

    async def _override():
        return _candidate_user()

    app.dependency_overrides[get_current_user] = _override
    try:
        _, session = await _seed_other_user_with_session("adminreport@example.com", "Admin Report")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/admin/sessions/{session.id}/report")
        assert response.status_code == 403
    finally:
        async def _restore():
            return TEST_USER

        app.dependency_overrides[get_current_user] = _restore
