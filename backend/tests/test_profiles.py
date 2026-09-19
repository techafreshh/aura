"""Tests for per-role profiles, the recruiter capability flag, and interviews from profile."""
import itertools
import json

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from api.main import app
from api.deps import get_current_user
from db.database import async_session
from db.crud import create_invite, get_candidate_profile, get_recruiter_profile
from db.models import User
from models.schemas import ParsedResumeProfile


class _StubUser:
    def __init__(self, id="test-user-id", email="test@example.com", name="Test User",
                 role="admin", is_recruiter=False):
        self.id = id
        self.email = email
        self.name = name
        self.role = role
        self.is_recruiter = is_recruiter
        self.avatar_url = None


def override_user(user):
    async def _override(request=None):
        return user
    app.dependency_overrides[get_current_user] = _override


@pytest.fixture(autouse=True)
def _leave_default_auth_override():
    """Re-apply the conftest TEST_USER override after each test (see test_invites)."""
    yield
    import conftest as _conftest

    async def _default_override(request=None):
        return _conftest.TEST_USER

    app.dependency_overrides[get_current_user] = _default_override


_client_counter = itertools.count(1)
_user_counter = itertools.count(1)


def _client():
    ip = f"10.7.{next(_client_counter)}.1"
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"X-Forwarded-For": ip})


async def _make_user(role="candidate", is_recruiter=False):
    n = next(_user_counter)
    stub = _StubUser(
        id=f"profile-user-{n}", email=f"profile-{n}@example.com",
        name="Profile Pat", role=role, is_recruiter=is_recruiter,
    )
    async with async_session() as db:
        existing = await db.get(User, stub.id)
        if existing is None:
            db.add(User(
                id=stub.id,
                email=stub.email,
                name=stub.name,
                provider="google",
                provider_id=f"{stub.id}-provider-id",
                role=role,
                is_recruiter=is_recruiter,
            ))
            await db.commit()
    override_user(stub)
    return stub


# ---------------------------------------------------------------- candidate profile


@pytest.mark.asyncio
async def test_get_candidate_profile_returns_empty_defaults():
    await _make_user()
    async with _client() as ac:
        resp = await ac.get("/profile/candidate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["headline"] == ""
    assert body["skills"] == []
    assert body["experience"] == []
    assert body["resume_stored"] is False


@pytest.mark.asyncio
async def test_put_and_get_candidate_profile_roundtrip():
    await _make_user()
    payload = {
        "headline": "Senior Backend Engineer",
        "location": "Berlin, DE",
        "summary": "Ships distributed systems.",
        "skills": ["Python", "Postgres", "Go"],
        "experience": [{"title": "Staff Engineer", "company": "Acme",
                        "start": "2022-01", "end": "", "description": "Built things."}],
        "education": [{"school": "TU Berlin", "degree": "MSc", "field": "CS",
                       "start": "2015", "end": "2017"}],
        "linkedin_url": "https://linkedin.com/in/pp",
        "github_url": "https://github.com/pp",
        "portfolio_url": None,
    }
    async with _client() as ac:
        put = await ac.put("/profile/candidate", json=payload)
        assert put.status_code == 200
        got = await ac.get("/profile/candidate")
    body = got.json()
    assert body["headline"] == "Senior Backend Engineer"
    assert body["skills"] == ["Python", "Postgres", "Go"]
    assert body["experience"][0]["company"] == "Acme"
    assert body["education"][0]["school"] == "TU Berlin"
    assert body["linkedin_url"] == "https://linkedin.com/in/pp"

    async with async_session() as db:
        row = await get_candidate_profile(db, "nobody")
    assert row is None  # sanity: no cross-user rows

    # JSON list columns round-trip through the DB, not just the response:
    async with async_session() as db:
        from db.models import CandidateProfile
        rows = (await db.execute(select(CandidateProfile))).scalars().all()
        assert len(rows) == 1
        assert json.loads(rows[0].skills_json) == ["Python", "Postgres", "Go"]


@pytest.mark.asyncio
async def test_candidate_profile_rejects_non_http_link():
    await _make_user()
    async with _client() as ac:
        resp = await ac.put("/profile/candidate", json={"github_url": "github.com/evil"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_candidate_profile_strips_html():
    await _make_user()
    async with _client() as ac:
        resp = await ac.put(
            "/profile/candidate",
            json={"headline": "<script>x</script>Engineer", "summary": "A" * 5000},
        )
    # Over-limit free text 422s (same convention as InviteCreate.context),
    # while the headline is tag-stripped and saved.
    assert resp.status_code == 422
    async with _client() as ac:
        resp = await ac.put("/profile/candidate", json={"headline": "<script>x</script>Engineer"})
    assert resp.status_code == 200
    assert resp.json()["headline"] == "Engineer"


# ---------------------------------------------------------------- resume parse


@pytest.mark.asyncio
async def test_resume_upload_stores_and_returns_parsed(monkeypatch):
    user = await _make_user()
    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: True)

    async def _extract(data):
        return "Jane Doe — Backend Engineer"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)
    parsed_out = ParsedResumeProfile(
        headline="Backend Engineer",
        skills=["Python"],
    )

    class _Result:
        output = parsed_out

    async def _run(text):
        return _Result()

    monkeypatch.setattr("api.profiles.profile_parser_agent.run", _run)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["headline"] == "Backend Engineer"
    assert body["parsed"]["skills"] == ["Python"]
    assert body["resume_stored"] is True

    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row.resume_stored is True
    # Parsed fields must NOT be auto-saved into the editable profile:
    assert row.headline == ""


@pytest.mark.asyncio
async def test_resume_upload_survives_agent_failure(monkeypatch):
    user = await _make_user()
    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: True)

    async def _extract(data):
        return "text"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    async def _boom(text):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("api.profiles.profile_parser_agent.run", _boom)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    assert resp.json()["parsed"] == {
        "headline": None, "location": None, "summary": None, "skills": [],
        "experience": [], "education": [], "linkedin_url": None,
        "github_url": None, "portfolio_url": None,
    }
    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row.resume_stored is True


@pytest.mark.asyncio
async def test_resume_upload_rejects_non_pdf():
    await _make_user()
    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.txt", b"hello", "text/plain")},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------- interview from profile


@pytest.mark.asyncio
async def test_interview_from_profile_creates_session(monkeypatch):
    user = await _make_user()
    async with async_session() as db:
        await upsert_profile_row(db, user.id)

    monkeypatch.setattr("api.profiles.get_resume", lambda uid: b"%PDF-1.4 fake")

    async def _extract(data):
        return "Jane — Backend Engineer"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    from models.schemas import InterviewPlan

    class _Result:
        output = InterviewPlan(
            candidate_name="Jane",
            extracted_skills=["Python"],
            question_bank=["Tell me about a system you designed."],
        )

    async def _run(text):
        return _Result()

    monkeypatch.setattr("api.profiles.interview_parser_agent.run", _run)

    async with _client() as ac:
        resp = await ac.post("/profile/candidate/interview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["plan_summary"]["candidate_name"] == "Jane"

    from db.models import InterviewSession
    async with async_session() as db:
        row = await db.get(InterviewSession, body["session_id"])
    assert row is not None
    assert row.user_id == user.id
    assert "question_bank" in row.plan_json


async def upsert_profile_row(db, user_id):
    """Give the user a stored resume so /profile/candidate/interview proceeds."""
    from db.crud import upsert_candidate_profile
    await upsert_candidate_profile(db, user_id, resume_stored=True)


@pytest.mark.asyncio
async def test_interview_from_profile_without_resume_404():
    await _make_user()
    async with _client() as ac:
        resp = await ac.post("/profile/candidate/interview")
    assert resp.status_code == 404


# ---------------------------------------------------------------- recruiter profile


@pytest.mark.asyncio
async def test_recruiter_profile_roundtrip():
    await _make_user(role="recruiter", is_recruiter=True)
    async with _client() as ac:
        put = await ac.put("/profile/recruiter", json={
            "company_name": "Acme Robotics",
            "job_title": "Engineering Manager",
            "company_website": "https://acme.example",
            "company_location": "Remote",
        })
        assert put.status_code == 200
        got = await ac.get("/profile/recruiter")
    body = got.json()
    assert body["company_name"] == "Acme Robotics"
    assert body["company_website"] == "https://acme.example"


@pytest.mark.asyncio
async def test_recruiter_profile_forbidden_for_plain_candidate():
    await _make_user(role="candidate", is_recruiter=False)
    async with _client() as ac:
        resp = await ac.get("/profile/recruiter")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recruiter_profile_allowed_via_flag_only():
    """A user who became a recruiter while role stayed 'candidate' passes the gate."""
    await _make_user(role="candidate", is_recruiter=True)
    async with _client() as ac:
        resp = await ac.get("/profile/recruiter")
    assert resp.status_code == 200
    assert resp.json() == {"company_name": "", "job_title": "", "company_website": None, "company_location": ""}


# ---------------------------------------------------------------- dual-role grant


@pytest.mark.asyncio
async def test_role_picker_grants_persistent_recruiter_flag():
    user = await _make_user(role="", is_recruiter=False)
    async with _client() as ac:
        first = await ac.post("/auth/role", json={"role": "recruiter"})
        assert first.status_code == 200
        assert first.json()["user"]["is_recruiter"] is True

        # Picking candidate later must NOT un-grant recruiter access.
        second = await ac.post("/auth/role", json={"role": "candidate"})
        assert second.status_code == 200
        data = second.json()
        assert data["user"]["role"] == "candidate"
        assert data["user"]["is_recruiter"] is True

    async with async_session() as db:
        row = await db.get(User, user.id)
    assert row.is_recruiter is True


# ---------------------------------------------------------------- invite branding


@pytest.mark.asyncio
async def test_invite_preview_shows_recruiter_company():
    recruiter = await _make_user(role="recruiter", is_recruiter=True)
    async with async_session() as db:
        await create_invite(
            db, recruiter_id=recruiter.id, title="Backend role", context=None,
            questions=["Q1?", "Q2?"], token="brand-token",
        )
        from db.crud import upsert_recruiter_profile
        await upsert_recruiter_profile(db, recruiter.id, company_name="Acme Robotics")

    async with _client() as ac:
        resp = await ac.get("/invite/brand-token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recruiter_company"] == "Acme Robotics"
    assert body["recruiter_name"] == "Profile Pat"
