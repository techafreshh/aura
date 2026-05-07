import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from agent.parser import agent
from utils.pdf_parser import extract_text_from_pdf
from models.schemas import UploadResponse

app = FastAPI(title="AI Interviewer API")

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
        
        return UploadResponse(
            session_id=session_id,
            plan_summary=result.output
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log the error here in a real application
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
