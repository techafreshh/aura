import uuid
import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from livekit.api import AccessToken, VideoGrants
from agent.parser import agent
from utils.pdf_parser import extract_text_from_pdf
from models.schemas import UploadResponse, InterviewPlan

app = FastAPI(title="AI Interviewer API")

plans: dict[str, InterviewPlan] = {}

@app.post("/upload", response_model=UploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        # Read file content
        file_bytes = await file.read()
        
        # Extract text from PDF
        text = await extract_text_from_pdf(file_bytes)
        
        # Run the AI Agent to parse the resume
        # Note: agent.run_sync is used here as a simple synchronous call, 
        # but in a real async environment agent.run might be preferred if available.
        # Pydantic AI's Agent.run is async.
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
        # Log the error here in a real application
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/plan/{session_id}", response_model=InterviewPlan)
async def get_plan(session_id: str):
    plan = plans.get(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Interview plan not found for the given session ID.")
    return plan

@app.get("/token")
async def get_token(session_id: str = Query(..., description="The session ID/room name to join")):
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

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

