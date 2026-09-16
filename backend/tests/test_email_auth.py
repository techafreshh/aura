"""Tests for email/password auth, email verification, and password reset.

SendByte sending is faked by monkeypatching ``api.auth.send_email`` (the name
the email task wrappers resolve at call time), so no network is touched and
triggered emails can be asserted on.
"""

import itertools
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

import api.main as main_module
from api import auth as auth_module
from api.auth import _hash_token, _hash_password, _new_token
from db.crud import get_user_by_email, store_verification_token, upsert_oauth_user
from db.database import async_session, _add_missing_user_columns
from db.models import User

TOKEN_RE = re.compile(r"token=([A-Za-z0-9_\-]+)")

_ip_counter = itertools.count(1)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test")


def _unique_email() -> str:
    return f"pw-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def ip_headers():
    """Unique per-test IP so rate limits (per X-Forwarded-For key) never bleed
    across tests."""
    return {"X-Forwarded-For": f"192.0.2.{next(_ip_counter)}"}


@pytest.fixture
def sent_emails(monkeypatch):
    sent: list[dict] = []

    async def _fake_send(to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})
        return True

    monkeypatch.setattr("api.auth.send_email", _fake_send)
    return sent


async def _create_password_user(email: str, *, verified: bool = False, role: str = "candidate") -> User:
    async with async_session() as db:
        user = User(
            email=email,
            name="PW User",
            provider="email",
            provider_id=email,
            password_hash=_hash_password("old-password-1"),
            email_verified=verified,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _get_user(email: str) -> User | None:
    async with async_session() as db:
        return await get_user_by_email(db, email)


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_sends_verification_email(self, ip_headers, sent_emails):
        email = _unique_email()
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1", "name": "Ada Lovelace"},
                headers=ip_headers,
            )
        assert resp.status_code == 200
        assert "verification" in resp.json()["message"].lower() or "check" in resp.json()["message"].lower()

        assert len(sent_emails) == 1
        assert sent_emails[0]["to"] == email
        raw_token = TOKEN_RE.search(sent_emails[0]["html"]).group(1)

        user = await _get_user(email)
        assert user is not None
        assert user.provider == "email"
        assert user.email_verified is False
        assert user.verification_token_hash == _hash_token(raw_token)
        assert user.password_hash and user.password_hash != "super-secret-1"

    @pytest.mark.asyncio
    async def test_register_duplicate_verified_rejected(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 409
        assert sent_emails == []

    @pytest.mark.asyncio
    async def test_register_duplicate_oauth_email_points_to_provider(self, ip_headers, sent_emails):
        email = _unique_email()
        # Create through the real OAuth path so this exercises the same
        # email_verified state upsert_oauth_user actually produces.
        async with async_session() as db:
            await upsert_oauth_user(db, email=email, name="OAuth User", provider="google", provider_id="g-1")
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 409
        assert "Google" in resp.json()["detail"]
        assert sent_emails == []

    @pytest.mark.asyncio
    async def test_register_duplicate_unverified_resends(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=False)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 200
        assert len(sent_emails) == 1
        user = await _get_user(email)
        assert user.email_verified is False
        # A fresh token replaced the old one
        assert user.verification_token_hash == _hash_token(TOKEN_RE.search(sent_emails[0]["html"]).group(1))

    @pytest.mark.asyncio
    async def test_register_concurrent_duplicate_does_not_500(self, ip_headers, sent_emails):
        """Losing the insert race must resolve to 409, not a 500.

        The pre-check is forced to miss the existing row (as it would for a
        concurrent registration), so the INSERT hits the unique constraint and
        the handler has to fall back to duplicate handling.
        """
        email = _unique_email()
        await _create_password_user(email, verified=True)

        real_get = auth_module.get_user_by_email
        calls = {"n": 0}

        async def _miss_once(db, value):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return await real_get(db, value)

        with patch.object(auth_module, "get_user_by_email", side_effect=_miss_once):
            async with _client() as ac:
                resp = await ac.post(
                    "/auth/register",
                    json={"email": email, "password": "super-secret-1"},
                    headers=ip_headers,
                )

        assert resp.status_code == 409
        assert sent_emails == []

    @pytest.mark.asyncio
    async def test_register_claims_legacy_unverified_oauth_account(self, ip_headers, sent_emails):
        """A legacy OAuth row the migration left email_verified=False must adopt
        the submitted password so verification enables password login.

        Regression: register previously issued a token but never stored the
        password, leaving the account permanently unable to sign in with one.
        """
        email = _unique_email()
        async with async_session() as db:
            db.add(User(email=email, name="Legacy OAuth", provider="google", provider_id="legacy-oauth"))
            await db.commit()

        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "chosen-password-1"},
                headers=ip_headers,
            )
            assert resp.status_code == 200
            assert len(sent_emails) == 1

            raw_token = TOKEN_RE.search(sent_emails[0]["html"]).group(1)
            await ac.get(f"/auth/verify-email?token={raw_token}", headers=ip_headers)
            login = await ac.post(
                "/auth/login",
                json={"email": email, "password": "chosen-password-1"},
                headers=ip_headers,
            )

        assert login.status_code == 200
        assert login.json()["token"]

    @pytest.mark.asyncio
    async def test_register_rejects_short_password(self, ip_headers, sent_emails):
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": _unique_email(), "password": "short", "name": "X"},
                headers=ip_headers,
            )
        # Rejected by the Pydantic request model before the handler runs
        assert resp.status_code == 422
        assert sent_emails == []

    @pytest.mark.asyncio
    async def test_register_rejects_invalid_email(self, ip_headers, sent_emails):
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": "not-an-email", "password": "super-secret-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 400
        assert sent_emails == []

    @pytest.mark.asyncio
    async def test_register_strips_html_from_name(self, ip_headers, sent_emails):
        email = _unique_email()
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1", "name": "<script>alert(1)</script>Ada"},
                headers=ip_headers,
            )
        assert resp.status_code == 200
        user = await _get_user(email)
        assert "<" not in user.name
        assert "Ada" in user.name


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, ip_headers):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/login",
                json={"email": email.upper(), "password": "old-password-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"]
        assert data["user"]["email"] == email
        assert "role" in data["user"]

    @pytest.mark.asyncio
    async def test_login_token_accepted_by_protected_endpoint(self, ip_headers):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/login",
                json={"email": email, "password": "old-password-1"},
                headers=ip_headers,
            )
        token = resp.json()["token"]

        # Bypass the conftest auth override to exercise the real JWT path
        saved = main_module.app.dependency_overrides.copy()
        main_module.app.dependency_overrides.pop(__import__("api.deps", fromlist=["get_current_user"]).get_current_user, None)
        try:
            async with _client() as ac:
                me = await ac.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        finally:
            main_module.app.dependency_overrides.update(saved)
        assert me.status_code == 200
        assert me.json()["email"] == email

    @pytest.mark.asyncio
    async def test_login_unverified_blocked_with_code(self, ip_headers):
        email = _unique_email()
        await _create_password_user(email, verified=False)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/login",
                json={"email": email, "password": "old-password-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "email_not_verified"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, ip_headers):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/login",
                json={"email": email, "password": "wrong-password"},
                headers=ip_headers,
            )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password."

    @pytest.mark.asyncio
    async def test_login_oauth_account_without_password(self, ip_headers):
        email = _unique_email()
        async with async_session() as db:
            await upsert_oauth_user(db, email=email, name="OAuth User", provider="github", provider_id="gh-1")
        async with _client() as ac:
            resp = await ac.post(
                "/auth/login",
                json={"email": email, "password": "some-password-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email(self, ip_headers):
        async with _client() as ac:
            resp = await ac.post(
                "/auth/login",
                json={"email": _unique_email(), "password": "whatever-123"},
                headers=ip_headers,
            )
        assert resp.status_code == 401


class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_verify_then_login(self, ip_headers, sent_emails):
        email = _unique_email()
        async with _client() as ac:
            await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1", "name": "Ada"},
                headers=ip_headers,
            )
        raw_token = TOKEN_RE.search(sent_emails[0]["html"]).group(1)

        async with _client() as ac:
            resp = await ac.get(
                "/auth/verify-email",
                params={"token": raw_token},
                headers=ip_headers,
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "status=success" in resp.headers["location"]

        user = await _get_user(email)
        assert user.email_verified is True
        assert user.verification_token_hash is None

        # Verification is a one-time token: reuse fails
        async with _client() as ac:
            again = await ac.get(
                "/auth/verify-email",
                params={"token": raw_token},
                headers=ip_headers,
                follow_redirects=False,
            )
        assert "status=invalid" in again.headers["location"]

        # And the account can now log in
        async with _client() as ac:
            login = await ac.post(
                "/auth/login",
                json={"email": email, "password": "super-secret-1"},
                headers=ip_headers,
            )
        assert login.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, ip_headers):
        email = _unique_email()
        user = await _create_password_user(email, verified=False)
        raw_token = _new_token()
        async with async_session() as db:
            db_user = await get_user_by_email(db, email)
            await store_verification_token(
                db, db_user, _hash_token(raw_token), datetime.now(timezone.utc) - timedelta(minutes=5)
            )

        async with _client() as ac:
            resp = await ac.get(
                "/auth/verify-email",
                params={"token": raw_token},
                headers=ip_headers,
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "status=expired" in resp.headers["location"]
        refreshed = await _get_user(email)
        assert refreshed.id == user.id
        assert refreshed.email_verified is False

    @pytest.mark.asyncio
    async def test_verify_missing_or_bogus_token(self, ip_headers):
        async with _client() as ac:
            none = await ac.get("/auth/verify-email", headers=ip_headers, follow_redirects=False)
            bogus = await ac.get(
                "/auth/verify-email",
                params={"token": "no-such-token"},
                headers=ip_headers,
                follow_redirects=False,
            )
        assert "status=invalid" in none.headers["location"]
        assert "status=invalid" in bogus.headers["location"]


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_resend_for_unverified_account(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=False)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/resend-verification",
                json={"email": email},
                headers=ip_headers,
            )
        assert resp.status_code == 200
        assert len(sent_emails) == 1
        assert sent_emails[0]["to"] == email

    @pytest.mark.asyncio
    async def test_resend_silent_for_verified_or_unknown(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            verified_resp = await ac.post(
                "/auth/resend-verification", json={"email": email}, headers=ip_headers
            )
            unknown_resp = await ac.post(
                "/auth/resend-verification", json={"email": _unique_email()}, headers=ip_headers
            )
        assert verified_resp.status_code == 200
        assert unknown_resp.status_code == 200
        assert sent_emails == []


class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_forgot_and_reset_round_trip(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            resp = await ac.post("/auth/forgot-password", json={"email": email}, headers=ip_headers)
        assert resp.status_code == 200
        assert len(sent_emails) == 1
        raw_token = TOKEN_RE.search(sent_emails[0]["html"]).group(1)

        async with _client() as ac:
            reset = await ac.post(
                "/auth/reset-password",
                json={"token": raw_token, "new_password": "brand-new-pw-1"},
                headers=ip_headers,
            )
        assert reset.status_code == 200

        # Old password no longer works, new one does; reset token is one-time
        async with _client() as ac:
            old_login = await ac.post(
                "/auth/login", json={"email": email, "password": "old-password-1"}, headers=ip_headers
            )
            new_login = await ac.post(
                "/auth/login", json={"email": email, "password": "brand-new-pw-1"}, headers=ip_headers
            )
            reuse = await ac.post(
                "/auth/reset-password",
                json={"token": raw_token, "new_password": "another-pw-123"},
                headers=ip_headers,
            )
        assert old_login.status_code == 401
        assert new_login.status_code == 200
        assert reuse.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_marks_unverified_account_verified(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=False)
        async with _client() as ac:
            await ac.post("/auth/forgot-password", json={"email": email}, headers=ip_headers)
        raw_token = TOKEN_RE.search(sent_emails[0]["html"]).group(1)
        async with _client() as ac:
            reset = await ac.post(
                "/auth/reset-password",
                json={"token": raw_token, "new_password": "brand-new-pw-1"},
                headers=ip_headers,
            )
        assert reset.status_code == 200
        user = await _get_user(email)
        assert user.email_verified is True

    @pytest.mark.asyncio
    async def test_forgot_silent_for_oauth_only_and_unknown(self, ip_headers, sent_emails):
        email = _unique_email()
        async with async_session() as db:
            await upsert_oauth_user(db, email=email, name="OAuth User", provider="google", provider_id="g-2")
        async with _client() as ac:
            oauth_resp = await ac.post("/auth/forgot-password", json={"email": email}, headers=ip_headers)
            unknown_resp = await ac.post("/auth/forgot-password", json={"email": _unique_email()}, headers=ip_headers)
        assert oauth_resp.status_code == 200
        assert unknown_resp.status_code == 200
        assert sent_emails == []

    @pytest.mark.asyncio
    async def test_reset_invalid_token(self, ip_headers):
        async with _client() as ac:
            resp = await ac.post(
                "/auth/reset-password",
                json={"token": "bogus-token-value-123", "new_password": "brand-new-pw-1"},
                headers=ip_headers,
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_rejects_short_password(self, ip_headers, sent_emails):
        email = _unique_email()
        await _create_password_user(email, verified=True)
        async with _client() as ac:
            await ac.post("/auth/forgot-password", json={"email": email}, headers=ip_headers)
        raw_token = TOKEN_RE.search(sent_emails[0]["html"]).group(1)
        async with _client() as ac:
            resp = await ac.post(
                "/auth/reset-password",
                json={"token": raw_token, "new_password": "short"},
                headers=ip_headers,
            )
        # Rejected by the Pydantic request model before the handler runs
        assert resp.status_code == 422


class TestUpsertCreatedFlag:
    @pytest.mark.asyncio
    async def test_created_flag_true_only_on_first_insert(self):
        email = _unique_email()
        async with async_session() as db:
            user, created_first = await upsert_oauth_user(
                db, email=email, name="A", provider="google", provider_id="p-1"
            )
            _, created_second = await upsert_oauth_user(
                db, email=email, name="B", provider="google", provider_id="p-1"
            )
        assert created_first is True
        assert created_second is False
        assert user.email_verified is True

    @pytest.mark.asyncio
    async def test_oauth_email_is_marked_verified_so_password_login_works(self, ip_headers):
        """An OAuth account must be email_verified from the start.

        Regression guard: the OAuth model path creates users with
        ``email_verified=False``, which left OAuth users unable to add a
        password and sign in (register only re-sent a token, and login then
        rejected the password because no hash was stored).
        """
        email = _unique_email()
        async with async_session() as db:
            await upsert_oauth_user(db, email=email, name="OAuth User", provider="google", provider_id="p-oauth")
        async with _client() as ac:
            resp = await ac.post(
                "/auth/register",
                json={"email": email, "password": "super-secret-1"},
                headers=ip_headers,
            )
        # Existing verified account -> 409 provider hint, not a token resend
        assert resp.status_code == 409
        assert "Google" in resp.json()["detail"]


class TestUserColumnMigration:
    @pytest.mark.asyncio
    async def test_adds_missing_columns_to_legacy_table(self, tmp_path):
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE users ("
                "id VARCHAR(36) PRIMARY KEY, email VARCHAR(255), name VARCHAR(255), "
                "avatar_url VARCHAR(512), provider VARCHAR(20), provider_id VARCHAR(255), "
                "role VARCHAR(20), created_at DATETIME, last_login_at DATETIME)"
            ))
        # Run twice: the second pass must be a no-op, not an error
        async with engine.begin() as conn:
            await _add_missing_user_columns(conn)
            await _add_missing_user_columns(conn)
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = {row[1] for row in result.fetchall()}
        await engine.dispose()

        assert {
            "password_hash",
            "email_verified",
            "verification_token_hash",
            "verification_token_expires_at",
            "reset_token_hash",
            "reset_token_expires_at",
        } <= columns
