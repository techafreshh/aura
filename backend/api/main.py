import uuid
import os
import json
import re
import html
import asyncio
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from livekit.api import AccessToken, VideoGrants
from langfuse import propagate_attributes
from agent.parser import agent
from utils.pdf_parser import extract_text_from_pdf
from utils.storage import archive_report, archive_transcript, get_artifact, archive_pdf
from utils.tracing import setup_langfuse
from models.schemas import UploadResponse, InterviewPlan, FinalReport, TranscriptPayload

import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    environment=os.getenv("ENVIRONMENT", "production"),
)

limiter = Limiter(
    key_func=lambda request: request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or get_remote_address(request),
    storage_uri=os.getenv("REDIS_URL"),
    in_memory_fallback_enabled=True,
)
app = FastAPI(title="AI Interviewer API")
setup_langfuse()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
env = os.getenv("ENVIRONMENT", "development")
if env == "production":
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

MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB

plans: dict[str, InterviewPlan] = {}
reports: dict[str, FinalReport] = {}
_sse_connections: dict[str, int] = {}
MAX_SSE_PER_SESSION = 3


def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown"
    # Strip dangerous tag pairs (with content)
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
    # Strip unclosed dangerous tags and everything after them
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<[^>]+>', '', name)
    name = html.escape(name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name


@app.post("/upload", response_model=UploadResponse)
@limiter.limit("10/hour")
async def upload_resume(request: Request, file: UploadFile = File(...)):
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        # Read file content
        file_bytes = await file.read()
        
        # Extract text from PDF
        text = await extract_text_from_pdf(file_bytes)
        
        # Run the AI Agent to parse the resume
        # Generate a unique session ID
        session_id = str(uuid.uuid4())

        with propagate_attributes(session_id=session_id):
            result = await agent.run(text)
        
        # Store the plan in memory
        plan = result.output
        plan.candidate_name = sanitize_name(plan.candidate_name) if plan.candidate_name else "Unknown"
        plans[session_id] = plan
        
        return UploadResponse(
            session_id=session_id,
            plan_summary=plan
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"UPLOAD ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/plan/{session_id}", response_model=InterviewPlan)
async def get_plan(session_id: str):
    plan = plans.get(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Interview plan not found for the given session ID.")
    return plan

@app.get("/token")
@limiter.limit("5/hour")
async def get_token(request: Request, session_id: str = Query(..., description="The session ID/room name to join")):
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500, 
            detail="LiveKit credentials are not configured on the server."
        )

    try:
        token = (
            AccessToken(api_key, api_secret)
            .with_identity("participant")
            .with_name("Candidate")
            .with_grants(VideoGrants(room_join=True, room=session_id))
            .to_jwt()
        )
        return {"token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")

@app.post("/report/{session_id}")
@limiter.limit("30/hour")
async def save_report(request: Request, session_id: str, report: FinalReport, background_tasks: BackgroundTasks):
    reports[session_id] = report

    def _archive():
        archive_report(session_id, report.model_dump(), b"")

    background_tasks.add_task(_archive)
    return {"status": "success"}

@app.get("/report/{session_id}", response_model=FinalReport)
async def get_report(session_id: str):
    report = reports.get(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found for the given session ID.")
    return report

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/transcript/{session_id}")
async def save_transcript(session_id: str, payload: TranscriptPayload, background_tasks: BackgroundTasks):
    def _archive():
        archive_transcript(
            session_id,
            payload.candidate_name,
            json.dumps([e.model_dump() for e in payload.entries]).encode()
        )
    background_tasks.add_task(_archive)
    return {"status": "success"}


@app.post("/upload-pdf/{session_id}")
async def upload_pdf(session_id: str, file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    report = reports.get(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Session not found")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MB limit")
    background_tasks.add_task(archive_pdf, session_id, report.candidate_name, pdf_bytes)
    return {"status": "success"}


@app.get("/download/{session_id}/{file_type}")
@limiter.limit("30/hour")
async def download_artifact(request: Request, session_id: str, file_type: str):
    report = reports.get(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Session not found")
    file_map = {"transcript": ("transcript.json", "application/json"), "pdf": ("report.pdf", "application/pdf")}
    entry = file_map.get(file_type)
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid file type. Use: transcript, pdf")
    filename, content_type = entry
    data = get_artifact(session_id, report.candidate_name, filename)
    if not data:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=data, media_type=content_type, headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/report-stream/{session_id}")
@limiter.limit("10/hour")
async def report_stream(request: Request, session_id: str):
    current = _sse_connections.get(session_id, 0)
    if current >= MAX_SSE_PER_SESSION:
        raise HTTPException(status_code=429, detail="Too many connections for this session")
    _sse_connections[session_id] = current + 1

    async def event_generator():
        try:
            for _ in range(120):  # 2 min timeout, check every 1s
                if await request.is_disconnected():
                    return
                report = reports.get(session_id)
                if report:
                    yield f"data: {json.dumps(report.model_dump())}\n\n"
                    return
                await asyncio.sleep(1)
            yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
        finally:
            new_count = max(0, _sse_connections.get(session_id, 1) - 1)
            if new_count == 0:
                _sse_connections.pop(session_id, None)
            else:
                _sse_connections[session_id] = new_count

    return StreamingResponse(event_generator(), media_type="text/event-stream")
