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
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Query, BackgroundTasks, Depends
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from livekit.api import AccessToken, VideoGrants
from langfuse import propagate_attributes
from agent.parser import agent
from utils.pdf_parser import extract_text_from_pdf
from utils.storage import archive_report, archive_transcript, get_artifact, archive_pdf, archive_audio
from utils.pdf_report import generate_report_pdf
from utils.tracing import setup_langfuse
from models.schemas import (
    UploadResponse,
    InterviewPlan,
    FinalReport,
    TranscriptPayload,
    SessionSummary,
    AdminSessionDetail,
    InviteCreate,
    InviteOut,
    InviteDetail,
    InvitePreview,
    InviteStartResponse,
    RecruiterInvitesResponse,
)
from api.deps import get_current_user, require_admin, require_recruiter
from api.rate_limit import limiter
from api.auth import router as auth_router
from api.profiles import router as profiles_router
from db.crud import (
    create_session,
    get_session,
    get_user_by_id,
    update_session_report,
    update_session_transcript,
    list_user_sessions,
    list_all_sessions,
    create_invite,
    get_invite_by_id,
    get_invite_by_token,
    get_invite_by_session,
    list_invites_for_recruiter,
    count_redeemed_invites_this_month,
    redeem_invite,
    release_invite_claim,
    complete_invite_by_session,
    get_recruiter_profile,
    CLAIMED,
    ALREADY_CLAIMED,
    CANCELLED,
)
from db.database import DATABASE_URL, async_session, init_db
from utils.config import ENVIRONMENT, OAUTH_SESSION_SECRET, RECRUITER_MONTHLY_LIMIT

import sentry_sdk

logger = logging.getLogger(__name__)

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    environment=ENVIRONMENT,
)

def _run_migrations() -> None:
    """Bring the database schema up to date with Alembic migrations.

    Two very different databases flow through here:

    - ``DATABASE_URL`` (Postgres, …): the server owns the schema lifecycle.
      An empty database builds the full schema from the migrations; an
      existing one upgrades in place. None of the SQLite file healing below
      applies — a legacy SQLite database cannot be reached this way at all.
    - SQLite file (default): auto-heals databases created by the earlier
      ``create_all``-only deploys: if the schema exists but has no
      ``alembic_version`` table, it is validated against the current models
      and then stamped at head instead of migrated. A schema that is missing
      tables or columns is *not* stamped — startup fails loudly instead of
      500ing later with an opaque ``no such column``.

    Runs synchronously — invoke via ``asyncio.to_thread`` so the event loop
    isn't blocked. For Postgres the Alembic invocation drives the app's async
    driver internally (see migrations/env.py), so this stays a plain sync
    call either way.
    """
    from alembic import command
    from alembic.config import Config

    from db.database import DB_PATH, Base, _find_missing_columns, _add_missing_user_columns_sqlite
    from db import models  # noqa: F401  (ensures all tables are registered on Base.metadata)

    backend_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_root / "alembic.ini"))

    if DATABASE_URL:
        try:
            command.upgrade(alembic_cfg, "head")
        except Exception as exc:
            logger.error(f"Database migration failed for the DATABASE_URL target: {exc}")
            raise RuntimeError(f"Database startup migrations failed: {exc}") from exc
        return

    if DB_PATH == ":memory:":
        # An in-memory SQLite DB lives inside a single connection; it starts
        # empty and the app's create_all safety net (init_db) builds it, so
        # there is nothing to migrate or stamp here.
        return

    try:
        import sqlite3

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
                # Additive tables (a table added to the models since the last
                # release) are created before the drift check: stamping at head
                # asserts the migrations ran, so the table must exist, and
                # init_db()'s create_all would build it moments later anyway.
                # Without this, a legacy DB missing any new table is refused at
                # startup instead of being brought up to date.
                Base.metadata.create_all(sync_engine)
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
app.include_router(profiles_router)

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
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB (~25 min of opus audio)

# Free-text sanitizers moved to utils.text so the profiles router can share
# them; re-exported here for backwards-compatible imports (tests, callers).
from utils.text import sanitize_name, sanitize_text  # noqa: E402, F401


async def can_access_session(session, user) -> bool:
    """Owner, admin, or the recruiter whose invite created the session."""
    if user.role == "admin":
        return True
    if session.user_id == user.id:
        return True
    async with async_session() as db:
        invite = await get_invite_by_session(db, session.id)
    return bool(invite and invite.recruiter_id == user.id)


@app.post("/upload", response_model=UploadResponse)
@limiter.limit("10/hour")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    job_description: str = Form(""),
    user=Depends(get_current_user),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        file_bytes = await file.read()
        text = await extract_text_from_pdf(file_bytes)
        jd = sanitize_text(job_description, 4000)

        session_id = str(uuid.uuid4())

        # When a job description is provided, steer the question generation
        # toward the target role (practice-interview mode).
        parser_input = text
        if jd:
            parser_input = (
                f"Candidate resume:\n{text}\n\n"
                f"Target job description:\n{jd}\n\n"
                "Tailor the interview questions to this job description as well as the resume."
            )

        with propagate_attributes(
            session_id=session_id,
            user_id=user.id,
        ):
            result = await agent.run(parser_input)

        plan = result.output
        plan.candidate_name = sanitize_name(plan.candidate_name) if plan.candidate_name else "Unknown"
        plan.job_description = jd or None

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
    # Owner, admin, or the recruiter whose invite created the session may read it.
    is_worker = getattr(user, "role", None) == "worker"
    if not is_worker and not await can_access_session(session, user):
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
        await complete_invite_by_session(db, session_id)

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

    if not await can_access_session(session, user):
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

    if not await can_access_session(session, user):
        raise HTTPException(status_code=403, detail="Access denied")

    file_map = {"transcript": ("transcript.json", "application/json"), "pdf": ("report.pdf", "application/pdf")}
    if file_type == "audio":
        # The browser recorder produces webm (Chrome/Firefox) or mp4 (Safari)
        data = get_artifact(session_id, session.candidate_name, "audio.webm")
        filename, content_type = "audio.webm", "audio/webm"
        if not data:
            data = get_artifact(session_id, session.candidate_name, "audio.mp4")
            filename, content_type = "audio.mp4", "audio/mp4"
        if not data:
            raise HTTPException(status_code=404, detail="Recording not found")
    else:
        entry = file_map.get(file_type)
        if not entry:
            raise HTTPException(status_code=400, detail="Invalid file type. Use: transcript, pdf, audio")
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


def _invite_out(invite, session=None) -> InviteOut:
    """Build an InviteOut, enriching with candidate/score info from the linked session."""
    from models.schemas import _extract_score, _extract_recommendation

    return InviteOut(
        invite_id=invite.id,
        title=invite.title,
        context=invite.context,
        questions=json.loads(invite.questions_json),
        token=invite.token,
        status=invite.status,
        created_at=invite.created_at,
        completed_at=invite.completed_at,
        candidate_user_id=invite.candidate_user_id,
        session_id=invite.session_id,
        candidate_name=session.candidate_name if session else None,
        overall_score=_extract_score(session.report_json) if session else None,
        recommendation=_extract_recommendation(session.report_json) if session else None,
    )


async def _get_owned_invite(db, invite_id: str, user):
    invite = await get_invite_by_id(db, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.recruiter_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return invite


@app.post("/recruiter/invites", response_model=InviteOut, status_code=201)
@limiter.limit("30/hour")
async def create_interview_invite(request: Request, payload: InviteCreate, user=Depends(get_current_user)):
    """Create an interview invite with 2-5 custom questions. Returns the shareable token."""
    require_recruiter(user)
    async with async_session() as db:
        invite = await create_invite(
            db,
            recruiter_id=user.id,
            title=payload.title.strip(),
            context=sanitize_text(payload.context, 4000) or None,
            questions=payload.questions,
            token=str(uuid.uuid4()),
        )
        return _invite_out(invite)


@app.get("/recruiter/invites", response_model=RecruiterInvitesResponse)
@limiter.limit("60/minute")
async def list_recruiter_invites(
    request: Request,
    user=Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """List the recruiter's invites with linked-session status, plus monthly quota usage."""
    require_recruiter(user)
    async with async_session() as db:
        invites = await list_invites_for_recruiter(db, user.id, limit=limit, offset=offset)
        quota_used = await count_redeemed_invites_this_month(db, user.id)

        session_ids = [i.session_id for i in invites if i.session_id]
        sessions = {}
        if session_ids:
            from sqlalchemy import select
            from db.models import InterviewSession
            result = await db.execute(
                select(InterviewSession).where(InterviewSession.id.in_(session_ids))
            )
            sessions = {s.id: s for s in result.scalars().all()}

    return RecruiterInvitesResponse(
        invites=[_invite_out(i, sessions.get(i.session_id)) for i in invites],
        quota_used=quota_used,
        quota_limit=RECRUITER_MONTHLY_LIMIT,
    )


@app.get("/recruiter/invites/{invite_id}", response_model=InviteDetail)
@limiter.limit("60/minute")
async def get_recruiter_invite(request: Request, invite_id: str, user=Depends(get_current_user)):
    """Full invite detail for the recruiter: questions, report, and transcript."""
    require_recruiter(user)
    async with async_session() as db:
        invite = await _get_owned_invite(db, invite_id, user)
        session = await get_session(db, invite.session_id) if invite.session_id else None

    detail = _invite_out(invite, session).model_dump()
    detail["report"] = (
        FinalReport.model_validate_json(session.report_json)
        if session and session.report_json else None
    )
    detail["transcript"] = (
        json.loads(session.transcript_json)
        if session and session.transcript_json else None
    )
    return detail


@app.post("/recruiter/invites/{invite_id}/cancel", response_model=InviteOut)
@limiter.limit("30/hour")
async def cancel_interview_invite(request: Request, invite_id: str, user=Depends(get_current_user)):
    """Cancel a pending invite so its link can no longer be redeemed."""
    require_recruiter(user)
    async with async_session() as db:
        invite = await _get_owned_invite(db, invite_id, user)
        if invite.status != "pending":
            raise HTTPException(status_code=409, detail="Only pending invites can be cancelled")
        if invite.candidate_user_id:
            # A redeemed-but-unfinished invite has a bound candidate and may
            # still complete; cancelling it would flip it back to "completed"
            # when the report lands, and the link is spent either way.
            raise HTTPException(
                status_code=409,
                detail="This invite has already been started by a candidate and can no longer be cancelled",
            )
        invite.status = "cancelled"
        await db.commit()
        await db.refresh(invite)
        return _invite_out(invite)


@app.get("/invite/{token}", response_model=InvitePreview)
@limiter.limit("60/minute")
async def get_invite_preview(request: Request, token: str, user=Depends(get_current_user)):
    """Candidate-facing invite preview: title, context, and questions."""
    async with async_session() as db:
        invite = await get_invite_by_token(db, token)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found")
        if invite.status == "cancelled":
            raise HTTPException(status_code=409, detail="This invite was cancelled")
        if invite.candidate_user_id and invite.candidate_user_id != user.id:
            raise HTTPException(status_code=403, detail="This invite has already been used")
        recruiter = await get_user_by_id(db, invite.recruiter_id)
        recruiter_profile = await get_recruiter_profile(db, invite.recruiter_id)

    return InvitePreview(
        title=invite.title,
        context=invite.context,
        questions=json.loads(invite.questions_json),
        recruiter_name=(recruiter.name if recruiter else "") or "Your recruiter",
        recruiter_company=(recruiter_profile.company_name if recruiter_profile else "") or None,
    )


@app.post("/invite/{token}/start", response_model=InviteStartResponse)
@limiter.limit("10/hour")
async def start_invited_interview(request: Request, token: str, user=Depends(get_current_user)):
    """Redeem an invite: bind the candidate, create the session, return the plan.

    No parser agent runs here — the recruiter's questions become the plan, so an
    invited interview costs voice minutes only. The monthly quota is enforced here
    because that is the moment credits start burning.
    """
    async with async_session() as db:
        invite = await get_invite_by_token(db, token)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found")
        if invite.status == "cancelled":
            raise HTTPException(status_code=409, detail="This invite was cancelled")
        if invite.candidate_user_id and invite.candidate_user_id != user.id:
            raise HTTPException(status_code=403, detail="This invite has already been used")

        # Idempotent: re-opening your own invite returns the same session.
        if invite.candidate_user_id == user.id and invite.session_id:
            session = await get_session(db, invite.session_id)
            if session:
                return InviteStartResponse(
                    session_id=session.id,
                    plan=InterviewPlan.model_validate_json(session.plan_json),
                )

        plan = InterviewPlan(
            candidate_name=sanitize_name(user.name) or "Candidate",
            extracted_skills=[],
            question_bank=json.loads(invite.questions_json),
            job_description=invite.context,
        )
        # Claim the invite *before* creating the session so single-use, the
        # cancelled guard, and the monthly quota are all one compare-and-swap:
        # concurrent starts race on this UPDATE, and only the winner goes on to
        # create a session. Checking the quota with a SELECT first would let two
        # starts on different invites of the same recruiter both pass.
        session_id = str(uuid.uuid4())
        reason = await redeem_invite(
            db,
            invite.id,
            candidate_user_id=user.id,
            session_id=session_id,
            recruiter_id=invite.recruiter_id,
            monthly_limit=RECRUITER_MONTHLY_LIMIT,
        )
        if reason != CLAIMED:
            if reason == ALREADY_CLAIMED:
                # Another request bound this invite first. If it was this same
                # candidate, hand back their session; otherwise the link is spent.
                # refresh() rather than a re-query: the session is not expired on
                # commit, so a re-query would hand back the stale cached row.
                await db.refresh(invite)
                if invite.candidate_user_id == user.id and invite.session_id:
                    existing = await get_session(db, invite.session_id)
                    if existing:
                        return InviteStartResponse(
                            session_id=existing.id,
                            plan=InterviewPlan.model_validate_json(existing.plan_json),
                        )
                raise HTTPException(status_code=403, detail="This invite has already been used")
            if reason == CANCELLED:
                raise HTTPException(status_code=409, detail="This invite was cancelled")
            raise HTTPException(
                status_code=403,
                detail="This recruiter has reached their monthly interview limit. Please try again next month.",
            )

        try:
            session = await create_session(
                db,
                user_id=user.id,
                candidate_name=plan.candidate_name,
                plan_json=plan.model_dump_json(),
                session_id=session_id,
            )
        except Exception:
            # Don't strand the invite pointing at a session that was never
            # written — release the claim so the candidate can try again.
            await release_invite_claim(db, invite.id)
            raise

    return InviteStartResponse(session_id=session.id, plan=plan)


@app.post("/audio/{session_id}")
@limiter.limit("10/hour")
async def upload_interview_audio(
    request: Request,
    session_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Upload the browser-recorded interview audio (webm/mp4) for archival."""
    async with async_session() as db:
        session = await get_session(db, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    ext = "mp4" if (file.filename or "").lower().endswith(".mp4") else "webm"
    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio exceeds 25 MB limit")
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    background_tasks.add_task(archive_audio, session_id, session.candidate_name, audio_bytes, ext)
    return {"status": "success"}
