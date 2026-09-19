"""Tests for the global error handlers registered in api/error_handlers.py.

Covers: the catch-all 500 (generic body, error_id, logged traceback), HTTP
exception normalization (detail preserved, context fields added), and the
compact 422 validation payload.
"""

import logging
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500_with_error_id(caplog):
    """A raised exception becomes a JSON 500 with a correlation id, no internals."""
    from fastapi import Depends, Request

    @app.get("/_boom_test")
    async def _boom(request: Request):  # pragma: no cover - simple raise
        raise RuntimeError("secret internal state leaked")

    try:
        # raise_app_exceptions=False: the ASGI transport must deliver the
        # ServerErrorMiddleware response instead of re-raising, matching what
        # a real ASGI server sends to the client.
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as ac:
            with caplog.at_level(logging.ERROR, logger="api.errors"):
                response = await ac.get("/_boom_test")
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/_boom_test"
        ]

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "An unexpected error occurred. Please try again later."
    assert "secret internal state" not in response.text
    assert body["error_id"]
    assert body["path"] == "/_boom_test"
    assert body["status"] == 500
    # The traceback, with the internal message, must be in the logs and carry
    # the same id as the response body.
    assert "secret internal state leaked" in caplog.text
    assert body["error_id"] in caplog.text


@pytest.mark.asyncio
async def test_http_exception_keeps_detail_and_adds_context():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/plan/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Interview plan not found for the given session ID."
    assert body["status"] == 404
    assert body["path"] == "/plan/does-not-exist"
    # 4xx responses get no error_id — only unhandled 500s do.
    assert "error_id" not in body


@pytest.mark.asyncio
async def test_validation_error_returns_compact_422():
    """Malformed JSON body against a typed endpoint yields a compact 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/recruiter/invites",
            json={"title": 123, "questions": "not-a-list"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert body["detail"]["message"] == "Validation failed for the provided data."
    errors = body["detail"]["errors"]
    assert isinstance(errors, list) and len(errors) >= 1
    assert all("field" in e and "message" in e for e in errors)


@pytest.mark.asyncio
async def test_unknown_api_route_returns_404_json():
    """JSON 404 (not nginx's HTML) for unknown paths — clients can parse it."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/definitely/not/a/route")

    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert body["path"] == "/definitely/not/a/route"
