import pytest
import os
import api.main as main_module
from httpx import AsyncClient, ASGITransport
from api.auth import _make_jwt
from db.database import async_session
from db.crud import upsert_user, get_user_by_id, create_session, get_session


def _get_app():
    return main_module.app


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_auth_unsupported_provider(self):
        async with AsyncClient(transport=ASGITransport(app=_get_app()), base_url="http://test") as ac:
            response = await ac.get("/auth/twitter")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_auth_me_returns_user(self):
        async with AsyncClient(transport=ASGITransport(app=_get_app()), base_url="http://test") as ac:
            response = await ac.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert "role" in data

    @pytest.mark.asyncio
    async def test_auth_logout(self):
        async with AsyncClient(transport=ASGITransport(app=_get_app()), base_url="http://test") as ac:
            response = await ac.post("/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestJWT:
    def test_make_jwt_returns_string(self):
        token = _make_jwt("user-123", "test@example.com", "admin", "Test User")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_make_jwt_contains_claims(self):
        import jwt as pyjwt
        secret = os.getenv("JWT_SECRET", "change-me-in-production")
        token = _make_jwt("user-123", "test@example.com", "admin", "Test User")
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["role"] == "admin"
        assert payload["name"] == "Test User"
        assert "exp" in payload


class TestCRUD:
    @pytest.mark.asyncio
    async def test_upsert_user_creates_new(self):
        async with async_session() as db:
            user = await upsert_user(
                db,
                email="crud-test@example.com",
                name="CRUD Test",
                provider="google",
                provider_id="12345",
            )
            assert user.email == "crud-test@example.com"
            assert user.name == "CRUD Test"
            assert user.role == "candidate"
            assert user.id is not None

    @pytest.mark.asyncio
    async def test_upsert_user_updates_existing(self):
        async with async_session() as db:
            user1 = await upsert_user(
                db,
                email="update-test@example.com",
                name="Original",
                provider="google",
                provider_id="111",
            )
            user2 = await upsert_user(
                db,
                email="update-test@example.com",
                name="Updated",
                provider="google",
                provider_id="111",
            )
            assert user1.id == user2.id
            assert user2.name == "Updated"

    @pytest.mark.asyncio
    async def test_get_user_by_id(self):
        async with async_session() as db:
            user = await upsert_user(
                db,
                email="get-test@example.com",
                name="Get Test",
                provider="github",
                provider_id="999",
            )
            found = await get_user_by_id(db, user.id)
            assert found is not None
            assert found.email == "get-test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self):
        async with async_session() as db:
            found = await get_user_by_id(db, "nonexistent-id")
            assert found is None

    @pytest.mark.asyncio
    async def test_create_and_get_session(self):
        async with async_session() as db:
            user = await upsert_user(
                db,
                email="session-test@example.com",
                name="Session Test",
                provider="google",
                provider_id="777",
            )
            session = await create_session(
                db,
                user_id=user.id,
                candidate_name="Session Test",
                plan_json='{"candidate_name":"Session Test","extracted_skills":[],"question_bank":[]}',
            )
            assert session.user_id == user.id
            assert session.status == "pending"

            found = await get_session(db, session.id)
            assert found is not None
            assert found.candidate_name == "Session Test"


class TestProtectedEndpoints:
    @pytest.mark.asyncio
    async def test_report_requires_auth(self):
        saved = _get_app().dependency_overrides.copy()
        _get_app().dependency_overrides.clear()
        try:
            async with AsyncClient(transport=ASGITransport(app=_get_app()), base_url="http://test") as ac:
                response = await ac.get("/report/nonexistent")
            assert response.status_code == 401
        finally:
            _get_app().dependency_overrides.update(saved)

    @pytest.mark.asyncio
    async def test_download_requires_auth(self):
        saved = _get_app().dependency_overrides.copy()
        _get_app().dependency_overrides.clear()
        try:
            async with AsyncClient(transport=ASGITransport(app=_get_app()), base_url="http://test") as ac:
                response = await ac.get("/download/nonexistent/transcript")
            assert response.status_code == 401
        finally:
            _get_app().dependency_overrides.update(saved)

    @pytest.mark.asyncio
    async def test_health_public(self):
        async with AsyncClient(transport=ASGITransport(app=_get_app()), base_url="http://test") as ac:
            response = await ac.get("/health")
        assert response.status_code == 200
