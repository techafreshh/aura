"""Global HTTP exception handlers for the API.

Registered once in ``api/main.py`` via ``register_error_handlers``. Every JSON
error response keeps the ``detail`` key FastAPI clients already expect, and
gains two correlation fields so problems can be matched against Sentry/Langfuse
logs:

- ``error_id``: UUID4 generated per response (matches the logged id for
  unhandled exceptions).
- ``path``: the request path that produced the error.

Handlers:

- ``HTTPException`` — normalized (adds the context fields, keeps detail).
- ``RequestValidationError`` — 422 with a compact list of field errors
  instead of FastAPI's default multi-KB validation dump.
- ``Exception`` — catch-all 500: the traceback goes to the error log (and
  Sentry, if configured) with an ``error_id``, the client only ever sees a
  generic message, never internal exception text.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("api.errors")

# Reasonable default when an HTTPException carries no usable detail.
_CLIENT_ERROR_FALLBACK = "Request failed."


def _error_payload(*, status: int, detail, request: Request, error_id: str | None = None) -> dict:
    payload: dict = {"detail": detail, "status": status, "path": request.url.path}
    if error_id:
        payload["error_id"] = error_id
    return payload


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        # Structured details (dict/list, e.g. {"code": "email_not_verified"})
        # pass through untouched — clients and tests key off them. Only empty
        # details are replaced with a plain fallback message.
        if detail is None or detail == "":
            detail = _CLIENT_ERROR_FALLBACK
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(status=exc.status_code, detail=detail, request=request),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        field_errors = [
            {
                "field": ".".join(str(part) for part in error.get("loc", []) if part != "body"),
                "message": error.get("msg", "Invalid value."),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                status=422,
                detail={"message": "Validation failed for the provided data.", "errors": field_errors},
                request=request,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        error_id = str(uuid.uuid4())
        logger.error(
            "Unhandled exception on %s %s [%s]: %s",
            request.method,
            request.url.path,
            error_id,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                status=500,
                detail="An unexpected error occurred. Please try again later.",
                request=request,
                error_id=error_id,
            ),
        )

    @app.middleware("http")
    async def request_timing_logging(request: Request, call_next):
        """Log every request at DEBUG and slow ones (>=1s) at WARNING.

        Query strings are deliberately omitted — they can carry tokens and
        one-time email links.
        """
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        log = logger.warning if duration_ms >= 1000 else logger.debug
        log(
            "%s %s -> %d (%.0f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
