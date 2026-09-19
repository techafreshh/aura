"""Tests for POST /rooms/{session_id}/close — the worker-only room teardown.

The agent's end_interview tool calls this after saving the report so an
agent-ended interview actually disconnects the candidate instead of leaving
them in a silent room with a running timer.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from api.main import app
from models.schemas import InterviewPlan
from db.database import async_session
from db.crud import create_session


async def _create_session(candidate: str = "Room Close") -> str:
    plan = InterviewPlan(candidate_name=candidate, extracted_skills=[], question_bank=[])
    async with async_session() as db:
        session = await create_session(
            db,
            user_id="test-user-id",
            candidate_name=candidate,
            plan_json=plan.model_dump_json(),
        )
    return session.id


def _lk_env() -> dict:
    return {
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "test-key",
        "LIVEKIT_API_SECRET": "test-secret",
    }


@pytest.mark.asyncio
async def test_close_room_rejects_non_worker():
    """The default auth override is an admin — worker-only, so 403."""
    session_id = await _create_session("Not Worker")
    with patch.dict(os.environ, _lk_env()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(f"/rooms/{session_id}/close")
    assert response.status_code == 403
    assert "Worker access required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_close_room_unknown_session_404():
    session_id = await _create_session()
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                f"/rooms/{session_id}-does-not-exist/close",
                headers={"Authorization": "Bearer test-worker-key"},
            )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.update(saved)


@pytest.mark.asyncio
async def test_close_room_success_deletes_room():
    session_id = await _create_session("Close Me")
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    try:
        with patch.dict(os.environ, _lk_env()), patch("api.main.LiveKitAPI") as mock_cls:
            instance = mock_cls.return_value
            instance.__aenter__.return_value = instance
            instance.room.delete_room = AsyncMock()

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    f"/rooms/{session_id}/close",
                    headers={"Authorization": "Bearer test-worker-key"},
                )

        assert response.status_code == 200
        assert response.json() == {"status": "closed"}
        instance.room.delete_room.assert_awaited_once()
        request = instance.room.delete_room.await_args[0][0]
        assert request.room == session_id
    finally:
        app.dependency_overrides.update(saved)


@pytest.mark.asyncio
async def test_close_room_livekit_failure_502():
    session_id = await _create_session("Close Fail")
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    try:
        with patch.dict(os.environ, _lk_env()), patch("api.main.LiveKitAPI") as mock_cls:
            instance = mock_cls.return_value
            instance.__aenter__.return_value = instance
            instance.room.delete_room = AsyncMock(side_effect=Exception("room api down"))

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    f"/rooms/{session_id}/close",
                    headers={"Authorization": "Bearer test-worker-key"},
                )

        assert response.status_code == 502
        assert "Failed to close room" in response.json()["detail"]
    finally:
        app.dependency_overrides.update(saved)


@pytest.mark.asyncio
async def test_close_room_requires_livekit_credentials():
    session_id = await _create_session("No Creds")
    saved = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    try:
        env = _lk_env()
        env["LIVEKIT_URL"] = ""  # falsy -> treated as unconfigured
        with patch.dict(os.environ, env):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    f"/rooms/{session_id}/close",
                    headers={"Authorization": "Bearer test-worker-key"},
                )
        assert response.status_code == 500
        assert "LiveKit credentials are not configured" in response.json()["detail"]
    finally:
        app.dependency_overrides.update(saved)
