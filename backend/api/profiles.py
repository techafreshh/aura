"""Per-role profile endpoints (candidate job-board profile, recruiter company profile).

Rationale for the shapes:
- GET returns an empty-but-complete profile when no row exists yet, so the
  frontend form can always initialize from the response without a null check.
- POST /profile/candidate/resume stores the PDF and runs the profile parser
  agent but NEVER writes parsed fields to the profile — the client prefills
  its form for review and only PUT persists them.
- POST /interviews/from-profile re-parses the stored resume with the existing
  interview parser agent so returning candidates skip the file upload.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import sentry_sdk
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from langfuse import propagate_attributes

from agent.parser import agent as interview_parser_agent
from agent.profile_parser import agent as profile_parser_agent
from api.deps import get_current_user, require_recruiter
from api.rate_limit import limiter
from db.crud import (
    create_session,
    get_candidate_profile,
    get_recruiter_profile,
    upsert_candidate_profile,
    upsert_recruiter_profile,
)
from db.database import async_session
from models.schemas import (
    CandidateProfileIn,
    CandidateProfileOut,
    InterviewPlan,
    ParsedResumeProfile,
    RecruiterProfileIn,
    RecruiterProfileOut,
    ResumeParseResponse,
    UploadResponse,
)
from utils.pdf_parser import extract_text_from_pdf
from utils.storage import archive_resume, get_resume
from utils.text import sanitize_name, sanitize_rich_text

logger = logging.getLogger("profiles")

router = APIRouter(prefix="/profile", tags=["profiles"])

MAX_RESUME_SIZE = 10 * 1024 * 1024  # 10 MB — matches the /upload-pdf limit


def _strip_html(text: str) -> str:
    """Sanitize free-text profile fields (drops active-tag content too)."""
    return sanitize_rich_text(text, max_length=10**9)


def _candidate_fields(payload: CandidateProfileIn) -> dict:
    """Validated schema -> ORM kwargs (lists serialized to JSON Text columns)."""
    return {
        "headline": _strip_html(payload.headline)[:200],
        "location": _strip_html(payload.location)[:120],
        "summary": _strip_html(payload.summary)[:4000],
        "skills_json": json.dumps(payload.skills),
        "experience_json": json.dumps([e.model_dump() for e in payload.experience]),
        "education_json": json.dumps([e.model_dump() for e in payload.education]),
        "linkedin_url": payload.linkedin_url,
        "github_url": payload.github_url,
        "portfolio_url": payload.portfolio_url,
    }


@router.get("/candidate", response_model=CandidateProfileOut)
async def read_candidate_profile(user=Depends(get_current_user)):
    """The caller's candidate profile; empty defaults when never saved."""
    async with async_session() as db:
        profile = await get_candidate_profile(db, user.id)
    if profile is None:
        return CandidateProfileOut()
    return CandidateProfileOut.from_row(profile)


@router.put("/candidate", response_model=CandidateProfileOut)
@limiter.limit("60/minute")
async def save_candidate_profile(request: Request, payload: CandidateProfileIn, user=Depends(get_current_user)):
    """Create or update the caller's candidate profile."""
    async with async_session() as db:
        profile = await upsert_candidate_profile(db, user.id, **_candidate_fields(payload))
    return CandidateProfileOut.from_row(profile)


@router.post("/candidate/resume", response_model=ResumeParseResponse)
@limiter.limit("10/hour")
async def upload_profile_resume(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Store the candidate's resume PDF and return parsed fields for review.

    Nothing is written to the profile's editable fields here — the client
    prefills empty form fields and the user saves explicitly. If the parser
    agent fails, the resume is still stored (it is what powers "start
    interview from profile") and an empty `parsed` is returned.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=413, detail="Resume exceeds 10 MB limit")
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    resume_stored = archive_resume(user.id, pdf_bytes)
    if not resume_stored:
        logger.error("Resume storage failed for user %s", user.id)

    parsed = ParsedResumeProfile()
    try:
        text = await extract_text_from_pdf(pdf_bytes)
        with propagate_attributes(user_id=user.id):
            result = await profile_parser_agent.run(text)
        parsed = result.output
    except Exception as exc:
        logger.error("Profile parse failed for user %s: %s", user.id, exc)
        sentry_sdk.capture_exception(exc)

    async with async_session() as db:
        await upsert_candidate_profile(
            db,
            user.id,
            resume_stored=resume_stored,
            resume_uploaded_at=datetime.now(timezone.utc),
        )

    return ResumeParseResponse(parsed=parsed, resume_stored=resume_stored)


@router.get("/recruiter", response_model=RecruiterProfileOut)
@limiter.limit("60/minute")
async def read_recruiter_profile(request: Request, user=Depends(get_current_user)):
    """The caller's recruiter profile; empty defaults when never saved."""
    require_recruiter(user)
    async with async_session() as db:
        profile = await get_recruiter_profile(db, user.id)
    if profile is None:
        return RecruiterProfileOut()
    return RecruiterProfileOut(
        company_name=profile.company_name,
        job_title=profile.job_title,
        company_website=profile.company_website,
        company_location=profile.company_location,
    )


@router.put("/recruiter", response_model=RecruiterProfileOut)
@limiter.limit("60/minute")
async def save_recruiter_profile(request: Request, payload: RecruiterProfileIn, user=Depends(get_current_user)):
    """Create or update the caller's recruiter profile. Requires recruiter access."""
    require_recruiter(user)
    async with async_session() as db:
        profile = await upsert_recruiter_profile(
            db,
            user.id,
            company_name=_strip_html(payload.company_name)[:200],
            job_title=_strip_html(payload.job_title)[:120],
            company_website=payload.company_website,
            company_location=_strip_html(payload.company_location)[:120],
        )
    return RecruiterProfileOut(
        company_name=profile.company_name,
        job_title=profile.job_title,
        company_website=profile.company_website,
        company_location=profile.company_location,
    )


@router.post("/candidate/interview", response_model=UploadResponse)
@limiter.limit("10/hour")
async def start_interview_from_profile(request: Request, user=Depends(get_current_user)):
    """Start a practice interview from the stored resume — no re-upload.

    Fetches the resume PDF archived by POST /profile/candidate/resume,
    re-extracts its text, and runs the same interview parser agent as
    POST /upload, so the created session is identical in shape and the
    standard /plan → /token voice flow works unchanged.
    """
    pdf_bytes = get_resume(user.id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="No resume on file. Upload one on your profile first.")

    try:
        text = await extract_text_from_pdf(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_id = str(uuid.uuid4())
    try:
        with propagate_attributes(session_id=session_id, user_id=user.id):
            result = await interview_parser_agent.run(text)
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
        return UploadResponse(session_id=session_id, plan_summary=plan)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Interview-from-profile failed for user %s: %s", user.id, e)
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
