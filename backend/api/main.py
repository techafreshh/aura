import uuid
import os
import json
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from livekit.api import AccessToken, VideoGrants
from agent.parser import agent
from utils.pdf_parser import extract_text_from_pdf
from utils.storage import archive_report, archive_transcript, get_artifact, archive_pdf
from models.schemas import UploadResponse, InterviewPlan, FinalReport

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL"),
    in_memory_fallback_enabled=True,
)
app = FastAPI(title="AI Interviewer API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
origins = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
if os.getenv("DOMAIN"):
    origins.append(os.getenv("DOMAIN"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

plans: dict[str, InterviewPlan] = {}
reports: dict[str, FinalReport] = {}

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
        result = await agent.run(text)
        
        # Generate a unique session ID
        session_id = str(uuid.uuid4())
        
        # Store the plan in memory
        plans[session_id] = result.output
        
        return UploadResponse(
            session_id=session_id,
            plan_summary=result.output
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
@limiter.limit("2/hour")
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
async def save_report(session_id: str, report: FinalReport, background_tasks: BackgroundTasks):
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
async def save_transcript(session_id: str, payload: dict, background_tasks: BackgroundTasks):
    def _archive():
        archive_transcript(session_id, payload.get("candidate_name", "unknown"), json.dumps(payload.get("entries", [])).encode())
    background_tasks.add_task(_archive)
    return {"status": "success"}


@app.post("/upload-pdf/{session_id}")
async def upload_pdf(session_id: str, file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    report = reports.get(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Session not found")
    pdf_bytes = await file.read()
    background_tasks.add_task(archive_pdf, session_id, report.candidate_name, pdf_bytes)
    return {"status": "success"}


@app.get("/download/{session_id}/{file_type}")
async def download_artifact(session_id: str, file_type: str):
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

