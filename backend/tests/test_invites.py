"""Tests for recruiter invites, role picker, quota, audio, and access control."""
import asyncio
import itertools
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError
from sqlalchemy import select

from api.main import app
from api.deps import get_current_user
from models.schemas import InterviewPlan, InviteCreate
from db.database import async_session
from db.crud import create_session, create_invite, get_invite_by_token
from db.models import InterviewSession, User


class _StubUser:
    def __init__(self, id="test-user-id", email="test@example.com", name="Test User", role="admin"):
        self.id = id
        self.email = email
        self.name = name
        self.role = role
        self.avatar_url = None


def override_user(user):
    async def _override(request=None):
        return user
    app.dependency_overrides[get_current_user] = _override


def use_real_auth():
    """Drop the conftest override so requests exercise the real get_current_user
    (needed to test the WORKER_API_KEY sentinel path)."""
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _leave_default_auth_override():
    """Re-apply the conftest TEST_USER override after each test in this file.

    Tests here install per-role stub overrides (and pop them entirely for the
    worker path). conftest's autouse fixture re-applies its override *before*
    each test but on the *current* api.main.app — and test_api/test_rate_limiting
    reload that module mid-suite, so files holding a pre-reload app reference
    (test_storage, test_transcript) would otherwise inherit whatever stub this
    file left behind and fail with 401/403.
    """
    yield
    import conftest as _conftest

    async def _default_override(request=None):
        return _conftest.TEST_USER

    app.dependency_overrides[get_current_user] = _default_override


_client_counter = itertools.count(1)
_user_counter = itertools.count(1)


def _client():
    """Unique X-Forwarded-For per client so slowapi buckets never collide across tests."""
    ip = f"10.1.{next(_client_counter)}.1"
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"X-Forwarded-For": ip})


async def _ensure_user(stub: _StubUser, provider: str):
    async with async_session() as db:
        existing = await db.get(User, stub.id)
        if existing is None:
            db.add(User(
                id=stub.id,
                email=stub.email,
                name=stub.name,
                provider=provider,
                provider_id=f"{stub.id}-provider-id",
                role=stub.role,
            ))
            await db.commit()
    return stub


async def _make_recruiter(name="Recruiter Rita", role="recruiter"):
    n = next(_user_counter)
    stub = await _ensure_user(
        _StubUser(id=f"recruiter-{n}", email=f"recruiter-{n}@example.com", name=name, role=role),
        "google",
    )
    override_user(stub)
    return stub


async def _make_candidate(name="Carl Candidate", role="candidate"):
    n = next(_user_counter)
    stub = await _ensure_user(
        _StubUser(id=f"candidate-{n}", email=f"candidate-{n}@example.com", name=name, role=role),
        "github",
    )
    override_user(stub)
    return stub


async def _invite_id(token):
    async with async_session() as db:
        invite = await get_invite_by_token(db, token)
        return invite.id


async def _start_invite_and_report(recruiter, token):
    """Redeem an invite as the candidate and save a report via the real worker path."""
    candidate = await _make_candidate()
    async with _client() as ac:
        start = await ac.post(f"/invite/{token}/start")
        assert start.status_code == 200
        session_id = start.json()["session_id"]

    use_real_auth()
    report = {
        "candidate_name": "Carl Candidate", "overall_score": 72,
        "section_grades": [{"section_name": "Technical", "score": 7, "comments": "Solid."}],
        "strengths": ["Go"], "weaknesses": ["SQL"], "recommendation": "Hire",
        "summary": "Did fine.",
    }
    async with _client() as ac:
        resp = await ac.post(f"/report/{session_id}", json=report,
                             headers={"Authorization": "Bearer test-worker-key"})
        assert resp.status_code == 200
    return session_id, candidate


# ---------------------------------------------------------------- role picker


@pytest.mark.asyncio
async def test_role_picker_sets_role():
    await _make_candidate(name="Picker Pat", role="")
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "recruiter"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] == "recruiter"
    assert data["token"]


@pytest.mark.asyncio
async def test_role_picker_rejects_admin():
    await _make_recruiter(name="Admin Andy", role="admin")
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "candidate"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_picker_rejects_worker():
    use_real_auth()
    async with _client() as ac:
        resp = await ac.post(
            "/auth/role", json={"role": "candidate"},
            headers={"Authorization": "Bearer test-worker-key"},
        )
    assert resp.status_code == 403


# ------------------------------------------------------------ invite creation


@pytest.mark.asyncio
async def test_invite_create_requires_recruiter_role():
    await _make_candidate(role="candidate")
    async with _client() as ac:
        resp = await ac.post("/recruiter/invites", json={
            "title": "Backend Engineer",
            "questions": ["Q1?", "Q2?"],
        })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_create_rejects_too_few_questions():
    await _make_recruiter()
    async with _client() as ac:
        resp = await ac.post("/recruiter/invites", json={
            "title": "Backend Engineer",
            "questions": ["Only one question?"],
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invite_create_rejects_too_many_questions():
    await _make_recruiter()
    async with _client() as ac:
        resp = await ac.post("/recruiter/invites", json={
            "title": "Backend Engineer",
            "questions": [f"Question {i}?" for i in range(6)],
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invite_create_success():
    await _make_recruiter()
    async with _client() as ac:
        resp = await ac.post("/recruiter/invites", json={
            "title": "Backend Engineer",
            "context": "We need a Go developer.",
            "questions": ["  Explain goroutines.  ", "How do you profile Go services?"],
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["token"]
    assert data["status"] == "pending"
    assert data["questions"] == ["Explain goroutines.", "How do you profile Go services?"]


def test_invite_create_schema_strips_and_bounds_questions():
    payload = InviteCreate(title="T", questions=["  a  ", "b"])
    assert payload.questions == ["a", "b"]
    with pytest.raises(ValidationError):
        InviteCreate(title="T", questions=["  ", "b"])
    with pytest.raises(ValidationError):
        InviteCreate(title="T", questions=["x" * 501, "b"])


# ------------------------------------------------------- candidate redemption


@pytest.mark.asyncio
async def test_invite_preview_and_start_synthesizes_plan_without_parser():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(
            db, recruiter_id=recruiter.id, title="Go Engineer",
            context="Building a payments platform.",
            questions=["Q1?", "Q2?"], token="tok-preview-start",
        )
        token = invite.token

    await _make_candidate()

    with patch("api.main.agent") as mock_agent:
        async with _client() as ac:
            preview = await ac.get(f"/invite/{token}")
            assert preview.status_code == 200
            assert preview.json()["recruiter_name"] == recruiter.name
            assert preview.json()["questions"] == ["Q1?", "Q2?"]

            resp = await ac.post(f"/invite/{token}/start")
    # The whole point: no parser agent call for invited interviews.
    mock_agent.run.assert_not_called()

    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"]["candidate_name"] == "Carl Candidate"
    assert data["plan"]["question_bank"] == ["Q1?", "Q2?"]
    assert data["plan"]["job_description"] == "Building a payments platform."


@pytest.mark.asyncio
async def test_invite_start_is_idempotent_for_same_candidate():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(
            db, recruiter_id=recruiter.id, title="Go Engineer", context=None,
            questions=["Q1?", "Q2?"], token="tok-idempotent",
        )
        token = invite.token

    await _make_candidate()
    async with _client() as ac:
        first = await ac.post(f"/invite/{token}/start")
        second = await ac.post(f"/invite/{token}/start")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] == second.json()["session_id"]


@pytest.mark.asyncio
async def test_invite_cannot_be_redeemed_by_two_candidates():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(
            db, recruiter_id=recruiter.id, title="Go Engineer", context=None,
            questions=["Q1?", "Q2?"], token="tok-single-use",
        )
        token = invite.token

    await _make_candidate(name="First Fred")
    async with _client() as ac:
        assert (await ac.post(f"/invite/{token}/start")).status_code == 200

    override_user(_StubUser(id="other-user-id", email="other@example.com",
                            name="Other Olive", role="candidate"))
    async with _client() as ac:
        resp = await ac.post(f"/invite/{token}/start")
        assert resp.status_code == 403
        preview = await ac.get(f"/invite/{token}")
        assert preview.status_code == 403


@pytest.mark.asyncio
async def test_invite_quota_blocks_redemption(monkeypatch):
    import api.main as main_module
    monkeypatch.setattr(main_module, "RECRUITER_MONTHLY_LIMIT", 1)

    recruiter = await _make_recruiter()
    async with async_session() as db:
        inv_a = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                    questions=["Q1?", "Q2?"], token="tok-quota-a")
        inv_b = await create_invite(db, recruiter_id=recruiter.id, title="B", context=None,
                                    questions=["Q1?", "Q2?"], token="tok-quota-b")
        tokens = [inv_a.token, inv_b.token]

    await _make_candidate()
    async with _client() as ac:
        assert (await ac.post(f"/invite/{tokens[0]}/start")).status_code == 200
        resp = await ac.post(f"/invite/{tokens[1]}/start")
    assert resp.status_code == 403
    assert "monthly interview limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cancelled_invite_rejects_start():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-cancel")
        invite_id = invite.id
        token = invite.token

    async with _client() as ac:
        resp = await ac.post(f"/recruiter/invites/{invite_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    await _make_candidate()
    async with _client() as ac:
        assert (await ac.post(f"/invite/{token}/start")).status_code == 409


@pytest.mark.asyncio
async def test_recruiter_invite_listing_includes_quota():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                            questions=["Q1?", "Q2?"], token="tok-list")
    async with _client() as ac:
        resp = await ac.get("/recruiter/invites")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["invites"]) == 1
    assert data["invites"][0]["title"] == "A"
    assert data["quota_limit"] > 0


# ------------------------------------------------------- deliverable access


@pytest.mark.asyncio
async def test_worker_can_fetch_plan():
    """Regression: the worker (WORKER_API_KEY) must be able to fetch /plan.

    Previously it received 403 and silently fell back to a generic plan.
    """
    plan = InterviewPlan(candidate_name="Worker Test", extracted_skills=[], question_bank=["Q1?"])
    async with async_session() as db:
        session = await create_session(db, user_id="candidate-user-id",
                                       candidate_name="Worker Test", plan_json=plan.model_dump_json())
        session_id = session.id

    use_real_auth()
    async with _client() as ac:
        resp = await ac.get(f"/plan/{session_id}",
                            headers={"Authorization": "Bearer test-worker-key"})
    assert resp.status_code == 200
    assert resp.json()["plan"]["candidate_name"] == "Worker Test"


@pytest.mark.asyncio
async def test_recruiter_can_access_candidate_report():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-access")
        token = invite.token

    session_id, _candidate = await _start_invite_and_report(recruiter, token)
    invite_id = await _invite_id(token)

    override_user(recruiter)
    async with _client() as ac:
        report = await ac.get(f"/report/{session_id}")
        assert report.status_code == 200
        assert report.json()["recommendation"] == "Hire"

        detail = await ac.get(f"/recruiter/invites/{invite_id}")
        assert detail.status_code == 200
        assert detail.json()["report"]["overall_score"] == 72
        assert detail.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_unrelated_user_cannot_access_report():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-no-access")
        token = invite.token

    session_id, _candidate = await _start_invite_and_report(recruiter, token)

    override_user(_StubUser(id="stranger-id", email="stranger@example.com",
                            name="Stranger", role="candidate"))
    async with _client() as ac:
        resp = await ac.get(f"/report/{session_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audio_upload_and_download():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-audio")
        token = invite.token

    session_id, candidate = await _start_invite_and_report(recruiter, token)

    # Candidate uploads the browser recording (same user owns the session)
    override_user(candidate)
    async with _client() as ac:
        resp = await ac.post(f"/audio/{session_id}",
                             files={"file": ("audio.webm", b"fake-audio-bytes", "audio/webm")})
        assert resp.status_code == 200

    # Recruiter can download it
    override_user(recruiter)
    with patch("api.main.get_artifact") as mock_get:
        mock_get.return_value = b"fake-audio-bytes"
        async with _client() as ac:
            resp = await ac.get(f"/download/{session_id}/audio")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/webm"
    assert resp.content == b"fake-audio-bytes"


@pytest.mark.asyncio
async def test_report_save_generates_real_pdf():
    """The archived report PDF must now contain real bytes (was b"")."""
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-pdf")
        token = invite.token

    session_id, _candidate = await _start_invite_and_report(recruiter, token)

    with patch("api.main.archive_report") as mock_archive:
        # Re-save to trigger the background task deterministically
        use_real_auth()
        report = {
            "candidate_name": "Carl Candidate", "overall_score": 80,
            "section_grades": [{"section_name": "Technical", "score": 8, "comments": "Good."}],
            "strengths": ["Go"], "weaknesses": [], "recommendation": "Hire", "summary": "OK.",
        }
        async with _client() as ac:
            await ac.post(f"/report/{session_id}", json=report,
                          headers={"Authorization": "Bearer test-worker-key"})
        mock_archive.assert_called_once()
        pdf_bytes = mock_archive.call_args[0][2]
        assert pdf_bytes.startswith(b"%PDF")


# --------------------------------------------------- concurrency & validation


@pytest.mark.asyncio
async def test_concurrent_start_binds_only_one_session(monkeypatch):
    """Two racing starts on the same token must not both create a session.

    The redemption claim is a conditional UPDATE; without it both requests pass
    the ``candidate_user_id is None`` check and both consume quota.
    """
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="Race", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-race")
        token = invite.token

    candidate = await _make_candidate()
    async with _client() as ac:
        first, second = await asyncio.gather(
            ac.post(f"/invite/{token}/start"),
            ac.post(f"/invite/{token}/start"),
        )

    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 200] or codes == [200, 403], codes

    # The real invariant: at most ONE session may exist for this candidate and
    # ONE redemption recorded — a check-then-act would let both requests through.
    async with async_session() as db:
        stored = await get_invite_by_token(db, token)
        assert stored.session_id
        assert stored.candidate_user_id == candidate.id

        owned = (await db.execute(
            select(InterviewSession).where(InterviewSession.user_id == candidate.id)
        )).scalars().all()
        assert len(owned) == 1, f"expected 1 session, got {len(owned)}"
        assert owned[0].id == stored.session_id

        # Any successful response must reference that same session.
        for resp in (first, second):
            if resp.status_code == 200:
                assert resp.json()["session_id"] == stored.session_id


@pytest.mark.asyncio
async def test_invite_redeem_claim_is_single_use_at_db_level():
    """`redeem_invite` returns CLAIMED once, then ALREADY_CLAIMED for the same invite."""
    from db.crud import redeem_invite, release_invite_claim, CLAIMED, ALREADY_CLAIMED
    from db.models import InterviewInvite

    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="CAS", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-cas")
        invite_id = invite.id

        assert await redeem_invite(db, invite_id, candidate_user_id="cand-a", session_id="sess-a") == CLAIMED
        # A second claim (different candidate, same invite) must lose.
        assert await redeem_invite(db, invite_id, candidate_user_id="cand-b", session_id="sess-b") == ALREADY_CLAIMED

        stored = await db.get(InterviewInvite, invite_id)
        assert stored.candidate_user_id == "cand-a"
        assert stored.session_id == "sess-a"

        # Releasing makes the link reusable again.
        await release_invite_claim(db, invite_id)
        await db.refresh(stored)
        assert stored.candidate_user_id is None and stored.session_id is None and stored.redeemed_at is None
        assert await redeem_invite(db, invite_id, candidate_user_id="cand-b", session_id="sess-b") == CLAIMED


@pytest.mark.asyncio
async def test_redeem_invite_enforces_quota_at_db_level():
    """The monthly-limit guard lives inside the atomic claim, not a pre-check.

    A pre-claim SELECT lets two concurrent starts on *different* invites of the
    same recruiter both pass and overshoot the quota.
    """
    from db.crud import redeem_invite, CLAIMED, QUOTA_EXCEEDED
    from db.models import InterviewInvite

    recruiter = await _make_recruiter()
    async with async_session() as db:
        inv_a = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                    questions=["Q1?", "Q2?"], token="tok-db-quota-a")
        inv_b = await create_invite(db, recruiter_id=recruiter.id, title="B", context=None,
                                    questions=["Q1?", "Q2?"], token="tok-db-quota-b")
        a_id, b_id = inv_a.id, inv_b.id

        assert await redeem_invite(db, a_id, candidate_user_id="c1", session_id="s1",
                                   recruiter_id=recruiter.id, monthly_limit=1) == CLAIMED
        # Second invite, same recruiter, limit already consumed.
        assert await redeem_invite(db, b_id, candidate_user_id="c2", session_id="s2",
                                   recruiter_id=recruiter.id, monthly_limit=1) == QUOTA_EXCEEDED

        # The blocked claim must not have bound the invite.
        stored = await db.get(InterviewInvite, b_id)
        assert stored.candidate_user_id is None and stored.redeemed_at is None


@pytest.mark.asyncio
async def test_redeem_invite_rejects_cancelled_at_db_level():
    """A cancelled invite cannot be redeemed, even before any candidate bound it."""
    from db.crud import redeem_invite, CANCELLED

    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="C", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-db-cancel")
        invite_id = invite.id
        invite.status = "cancelled"
        await db.commit()

    async with async_session() as db:
        assert await redeem_invite(db, invite_id, candidate_user_id="c1", session_id="s1") == CANCELLED


@pytest.mark.asyncio
async def test_started_invite_cannot_be_cancelled():
    """An invite whose candidate already started must not be cancellable —
    otherwise the report landing would flip a "cancelled" invite to "completed"."""
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-cancel-started")
        invite_id, token = invite.id, invite.token

    await _make_candidate()
    async with _client() as ac:
        assert (await ac.post(f"/invite/{token}/start")).status_code == 200

    override_user(recruiter)
    async with _client() as ac:
        resp = await ac.post(f"/recruiter/invites/{invite_id}/cancel")
    assert resp.status_code == 409
    assert "started" in resp.json()["detail"]


def test_invite_create_schema_rejects_whitespace_only_title():
    """`min_length=1` alone accepts "   ", which stores an empty title."""
    with pytest.raises(ValidationError):
        InviteCreate(title="   ", questions=["a?", "b?"])
    assert InviteCreate(title="  Backend Engineer  ", questions=["a?", "b?"]).title == "Backend Engineer"


# ------------------------------------------------------------------ expiry


@pytest.mark.asyncio
async def test_invite_create_defaults_to_24h_expiry():
    """Omitting expires_in_hours stores expires_at ≈ 24h out."""
    from utils.config import DEFAULT_INVITE_EXPIRY_HOURS

    await _make_recruiter()
    before = datetime.now(timezone.utc)
    async with _client() as ac:
        resp = await ac.post("/recruiter/invites", json={
            "title": "Backend Engineer",
            "questions": ["Q1?", "Q2?"],
        })
    assert resp.status_code == 201
    # SQLite round-trips datetimes naive; re-tag as UTC before comparing.
    expires_at = datetime.fromisoformat(resp.json()["expires_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    expected = timedelta(hours=DEFAULT_INVITE_EXPIRY_HOURS)
    # 2-minute slop for clock skew between the assertion and the request.
    assert before + expected - timedelta(minutes=2) <= expires_at <= datetime.now(timezone.utc) + expected + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_invite_create_custom_expiry_window():
    await _make_recruiter()
    async with _client() as ac:
        resp = await ac.post("/recruiter/invites", json={
            "title": "Backend Engineer",
            "questions": ["Q1?", "Q2?"],
            "expires_in_hours": 4,
        })
    assert resp.status_code == 201
    # SQLite round-trips datetimes naive; re-tag as UTC before comparing.
    expires_at = datetime.fromisoformat(resp.json()["expires_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    delta = expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=3, minutes=58) < delta < timedelta(hours=4, minutes=2)


def test_invite_create_schema_rejects_bad_expiry():
    with pytest.raises(ValidationError):
        InviteCreate(title="T", questions=["a?", "b?"], expires_in_hours=0)
    with pytest.raises(ValidationError):
        InviteCreate(title="T", questions=["a?", "b?"], expires_in_hours=721)
    assert InviteCreate(title="T", questions=["a?", "b?"], expires_in_hours=720).expires_in_hours == 720


@pytest.mark.asyncio
async def test_expired_invite_rejects_start_with_410():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-expired-start")
        invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.commit()
        token = invite.token

    await _make_candidate()
    async with _client() as ac:
        resp = await ac.post(f"/invite/{token}/start")
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_expired_invite_preview_returns_410():
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-expired-preview")
        invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.commit()
        token = invite.token

    await _make_candidate()
    async with _client() as ac:
        resp = await ac.get(f"/invite/{token}")
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_redeem_invite_reason_is_expired():
    """The atomic claim itself reports expiry (not already_claimed) for a dead link."""
    from db.crud import redeem_invite, EXPIRED

    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-expired-reason")
        invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.commit()
        invite_id = invite.id

    async with async_session() as db:
        reason = await redeem_invite(
            db, invite_id, candidate_user_id="candidate-x",
            session_id="sess-x", recruiter_id=recruiter.id, monthly_limit=20,
        )
    assert reason == EXPIRED


@pytest.mark.asyncio
async def test_started_invite_not_blocked_by_expiry():
    """Redemption is the expiry gate: a candidate who started in time re-opens
    their session idempotently even after expires_at passes."""
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-expired-idempotent",
                                     expires_in_hours=1)
        token = invite.token

    await _make_candidate()
    async with _client() as ac:
        first = await ac.post(f"/invite/{token}/start")
        assert first.status_code == 200
        session_id = first.json()["session_id"]

        # Age the link past its expiry, then re-open it as the same candidate.
        async with async_session() as db:
            row = await get_invite_by_token(db, token)
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()

        second = await ac.post(f"/invite/{token}/start")
        assert second.status_code == 200
        assert second.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_null_expiry_invite_never_expires():
    """Pre-feature invites have expires_at = NULL and stay redeemable."""
    recruiter = await _make_recruiter()
    async with async_session() as db:
        invite = await create_invite(db, recruiter_id=recruiter.id, title="A", context=None,
                                     questions=["Q1?", "Q2?"], token="tok-null-expiry")
        assert invite.expires_at is None
        token = invite.token

    await _make_candidate()
    async with _client() as ac:
        resp = await ac.post(f"/invite/{token}/start")
    assert resp.status_code == 200
