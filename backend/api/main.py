import uuid
import os
import json
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Query, BackgroundTasks, Depends
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from livekit.api import AccessToken, VideoGrants
from langfuse import propagate_attributes
from agent.parser import agent
from utils.pdf_parser import extract_text_from_pdf
from utils.storage import archive_report, archive_transcript, get_artifact, archive_pdf
from utils.pdf_report import generate_report_pdf
from utils.tracing import setup_langfuse
from models.schemas import UploadResponse, InterviewPlan, FinalReport, TranscriptPayload, SessionSummary, AdminSessionDetail
from api.deps import get_current_user, require_admin
from api.rate_limit import limiter
from api.auth import router as auth_router
from db.crud import create_session, get_session, get_user_by_id, update_session_report, update_session_transcript, list_user_sessions, list_all_sessions
from db.database import async_session, init_db
from utils.config import ENVIRONMENT, OAUTH_SESSION_SECRET

import sentry_sdk

logger = logging.getLogger(__name__)

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    environment=ENVIRONMENT,
)

def _run_migrations() -> None:
    """Bring the SQLite schema up to date with Alembic migrations.

    Auto-heals databases created by the earlier ``create_all``-only deploys:
    if the schema exists but has no ``alembic_version`` table, it is validated
    against the current models and then stamped at head instead of migrated.
    A schema that is missing tables or columns is *not* stamped — startup
    fails loudly instead of 500ing later with an opaque ``no such column``.
    Runs synchronously — invoke via ``asyncio.to_thread`` so the event loop
    isn't blocked.
    """
    import sqlite3

    from alembic import command
    from alembic.config import Config

    from db.database import DB_PATH, _find_missing_columns, _add_missing_user_columns_sqlite
    from db import models  # noqa: F401  (ensures all tables are registered on Base.metadata)

    if DB_PATH == ":memory:":
        # An in-memory SQLite DB lives inside a single connection; it starts
        # empty and the app's create_all safety net (init_db) builds it, so
        # there is nothing to migrate or stamp here.
        return

    backend_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_root / "alembic.ini"))

    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()

        if "alembic_version" in tables:
            command.upgrade(alembic_cfg, "head")
        elif "users" in tables:
            # Pre-Alembic create_all-era DB: bring post-release ``users``
            # columns up to the current model first, then validate the live
            # schema before stamping. Without the ALTER, the new email-auth
            # columns read as drift and the stamp is refused; without the
            # validation, a genuinely drifted legacy DB would be recorded as
            # "current" and fail later at request time.
            conn = sqlite3.connect(DB_PATH)
            try:
                _add_missing_user_columns_sqlite(conn)
                conn.commit()
            finally:
                conn.close()

            sync_engine = sa.create_engine(f"sqlite:///{DB_PATH}")
            try:
                with sync_engine.connect() as engine_conn:
                    missing = _find_missing_columns(engine_conn)
            finally:
                sync_engine.dispose()
            if missing:
                details = "; ".join(f"{table}: {', '.join(cols)}" for table, cols in missing.items())
                raise RuntimeError(
                    f"Pre-Alembic database schema is missing expected tables/columns: {details}. "
                    "Not stamping it as up to date. For dev, delete the database file and restart "
                    "to recreate the schema; for prod, restore a compatible backup or migrate manually."
                )
            command.stamp(alembic_cfg, "head")
        else:
            command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        logger.error(f"Database migration failed for {DB_PATH}: {exc}")
        raise RuntimeError(f"Database startup migrations failed: {exc}") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(_run_migrations)
    # Safety net behind the Alembic migrations: create_all is a no-op on a
    # fully migrated schema; it also backfills OAuth identities for users
    # created before multi-provider login and runs the dev-only drift guard.
    await init_db()
    yield


app = FastAPI(title="AI Interviewer API", lifespan=lifespan)
setup_langfuse()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)

# Add CORS middleware
if ENVIRONMENT == "production":
    domain = os.getenv("DOMAIN")
    if not domain:
        raise RuntimeError("DOMAIN env var is required in production")
    origins = [domain]
else:
    origins = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authlib's OAuth flow stores the CSRF state in the Starlette session, which
# requires SessionMiddleware; without it /auth/{provider} raises at runtime.
# Registered exactly once — the signing secret is resolved in utils/config.py.
app.add_middleware(
    SessionMiddleware,
    secret_key=OAUTH_SESSION_SECRET,
    https_only=(ENVIRONMENT == "production"),
    same_site="lax",
)

MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB


def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown"
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<[^>]+>', '', name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "Unknown"


@app.post("/upload", response_model=UploadResponse)
@limiter.limit("10/hour")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        file_bytes = await file.read()
        text = await extract_text_from_pdf(file_bytes)

        session_id = str(uuid.uuid4())

        with propagate_attributes(
            session_id=session_id,
            user_id=user.id,
        ):
            result = await agent.run(text)

        plan = result.output
        plan.candidate_name = sanitize_name(plan.candidate_name) if plan.candidate_name else "Unknown"

        async with async_session() as db:
            await create_session(
                db,
                user_id=user.id,
                candidate_name=plan.candidate_name,
                plan_json=plan.model_dump_json(),
                session_id=session_id,
            )

        return UploadResponse(
            session_id=session_id,
            plan_summary=plan,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"UPLOAD ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@app.get("/plan/{session_id}")
async def get_plan(session_id: str, request: Request, user=Depends(get_current_user)):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Interview plan not found for the given session ID.")

    # The worker fetches the plan with WORKER_API_KEY (same bypass as /report
    # and /transcript); without it the worker silently falls back to a generic plan.
    is_worker = getattr(user, "role", None) == "worker"
    if not is_worker and user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    async with async_session() as db:
        owner = await get_user_by_id(db, session.user_id)

    plan = InterviewPlan.model_validate_json(session.plan_json)
    return {
        "plan": plan,
        "user_id": session.user_id,
        "user_email": (owner.email if owner else "") or "",
    }


@app.get("/token")
@limiter.limit("5/hour")
async def get_token(
    request: Request,
    session_id: str = Query(..., description="The session ID/room name to join"),
    user=Depends(get_current_user),
):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="LiveKit credentials are not configured on the server.",
        )

    identity = getattr(user, "id", "participant") or "participant"
    try:
        token = (
            AccessToken(api_key, api_secret)
            .with_identity(identity)
            .with_name("Candidate")
            .with_grants(VideoGrants(room_join=True, room=session_id))
            .to_jwt()
        )
        return {"token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")


@app.post("/report/{session_id}")
@limiter.limit("30/hour")
async def save_report(
    request: Request,
    session_id: str,
    report: FinalReport,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    is_worker = getattr(user, "role", None) == "worker"
    if not is_worker and user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if is_worker:
        print(f"WORKER_REPORT_WRITE: worker={user.id} session_id={session_id} session_owner={session.user_id}")

    async with async_session() as db:
        await update_session_report(db, session_id, report.model_dump_json())

    def _archive():
        try:
            archive_report(session_id, report.model_dump(), generate_report_pdf(report))
        except Exception as exc:
            print(f"REPORT_ARCHIVE_ERROR: session_id={session_id} error={exc}")

    background_tasks.add_task(_archive)
    return {"status": "success"}


@app.get("/report/{session_id}", response_model=FinalReport)
async def get_report(session_id: str, user=Depends(get_current_user)):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Report not found for the given session ID.")

    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not session.report_json:
        raise HTTPException(status_code=404, detail="Report not yet available.")

    return FinalReport.model_validate_json(session.report_json)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/transcript/{session_id}")
async def save_transcript(
    session_id: str,
    payload: TranscriptPayload,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    is_worker = getattr(user, "role", None) == "worker"
    if not is_worker and user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    transcript_data = json.dumps([e.model_dump() for e in payload.entries])

    async with async_session() as db:
        await update_session_transcript(db, session_id, transcript_data)

    def _archive():
        archive_transcript(
            session_id,
            session.candidate_name,
            transcript_data.encode(),
        )
    background_tasks.add_task(_archive)
    return {"status": "success"}


@app.post("/upload-pdf/{session_id}")
async def upload_pdf(
    session_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    user=Depends(get_current_user),
):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MB limit")
    background_tasks.add_task(archive_pdf, session_id, session.candidate_name, pdf_bytes)
    return {"status": "success"}


@app.get("/download/{session_id}/{file_type}")
@limiter.limit("30/hour")
async def download_artifact(request: Request, session_id: str, file_type: str, user=Depends(get_current_user)):
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    file_map = {"transcript": ("transcript.json", "application/json"), "pdf": ("report.pdf", "application/pdf")}
    entry = file_map.get(file_type)
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid file type. Use: transcript, pdf")
    filename, content_type = entry
    data = get_artifact(session_id, session.candidate_name, filename)
    if not data and file_type == "pdf" and session.report_json:
        data = generate_report_pdf(FinalReport.model_validate_json(session.report_json))
    if not data and file_type == "transcript" and session.transcript_json:
        data = session.transcript_json.encode()
    if not data:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=data, media_type=content_type, headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/admin/sessions", response_model=list[SessionSummary])
@limiter.limit("60/minute")
async def admin_list_sessions(
    request: Request,
    user=Depends(get_current_user),
    status: Optional[str] = Query(None, pattern="^(pending|in_progress|completed)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """List all interview sessions across all users. Admin-only.

    Supports optional status filtering and pagination.
    """
    require_admin(user)
    async with async_session() as db:
        sessions = await list_all_sessions(db, limit=limit, offset=offset, status=status)
    return [SessionSummary.from_db(s) for s in sessions]


@app.get("/sessions/mine", response_model=list[SessionSummary])
@limiter.limit("60/minute")
async def list_my_sessions(
    request: Request,
    user=Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """List sessions owned by the current user. Requires authentication."""
    async with async_session() as db:
        sessions = await list_user_sessions(db, user.id, limit=limit, offset=offset)
    return [SessionSummary.from_db(s) for s in sessions]


@app.get("/sessions/{session_id}/detail", response_model=AdminSessionDetail)
@limiter.limit("60/minute")
async def get_my_session_detail(request: Request, session_id: str, user=Depends(get_current_user)):
    """Return a session's report and transcript to its owner or an admin."""
    async with async_session() as db:
        session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    async with async_session() as db:
        owner = await get_user_by_id(db, session.user_id)
    return AdminSessionDetail(
        session_id=session.id,
        candidate_name=session.candidate_name,
        user_email=(owner.email if owner else "") or "",
        user_id=session.user_id,
        plan=InterviewPlan.model_validate_json(session.plan_json) if session.plan_json else None,
        report=FinalReport.model_validate_json(session.report_json) if session.report_json else None,
        transcript=json.loads(session.transcript_json) if session.transcript_json else None,
        status=session.status,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )


@app.get("/admin/sessions/{session_id}/detail", response_model=AdminSessionDetail, status_code=200)
@limiter.limit("60/minute")
async def admin_get_session_detail(request: Request, session_id: str, user=Depends(get_current_user)):
    """Get full session detail including plan, report, and transcript. Admin-only."""
    require_admin(user)
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async with async_session() as db:
        owner = await get_user_by_id(db, session.user_id)

    return AdminSessionDetail(
        session_id=session.id,
        candidate_name=session.candidate_name,
        user_email=(owner.email if owner else "") or "",
        user_id=session.user_id,
        plan=InterviewPlan.model_validate_json(session.plan_json) if session.plan_json else None,
        report=FinalReport.model_validate_json(session.report_json) if session.report_json else None,
        transcript=json.loads(session.transcript_json) if session.transcript_json else None,
        status=session.status,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )


@app.get("/admin/sessions/{session_id}/report", response_model=FinalReport)
@limiter.limit("60/minute")
async def admin_get_session_report(request: Request, session_id: str, user=Depends(get_current_user)):
    """Get the final report for a session. Admin-only.

    Tries the database first, then falls back to MinIO for sessions
    that were persisted before the report column was added.
    """
    require_admin(user)
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.report_json:
        return FinalReport.model_validate_json(session.report_json)

    # Fallback to MinIO for sessions persisted before the DB report column existed
    data = get_artifact(session_id, session.candidate_name, "report.json")
    if data:
        return FinalReport.model_validate_json(data.decode())

    raise HTTPException(status_code=404, detail="Report not found")
