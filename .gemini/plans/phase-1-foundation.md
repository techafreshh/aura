# Feature: Phase 1: Foundation (Backend & Parsing)

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This phase establishes the foundational backend infrastructure for the AI Interviewer Agent. It sets up a FastAPI server and implements the `ResumeParserAgent` using Pydantic AI. The core functionality enables a user to upload a resume (PDF/Text), which is then parsed by an LLM to generate a structured `InterviewPlan` containing extracted skills and a baseline question bank.

## User Story

As a candidate
I want to upload my resume
So that the AI can ask me relevant questions about my specific experience.

## Problem Statement

To conduct a personalized interview, the system needs to ingest the candidate's resume and extract meaningful context (skills, experience) to form an interview plan and dynamically generate relevant questions.

## Solution Statement

Create a FastAPI backend with a `/upload` endpoint that accepts multipart form data. Implement a `ResumeParserAgent` using Pydantic AI that takes the extracted text from the uploaded document and outputs a strongly-typed `InterviewPlan` schema.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: Backend API, AI Agents
**Dependencies**: `fastapi`, `uvicorn`, `python-multipart`, `pydantic-ai`, `pypdf`, `python-dotenv`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

*(No existing codebase files as this is Phase 1 - starting fresh)*

### New Files to Create

- `backend/requirements.txt` - Project dependencies
- `backend/api/main.py` - FastAPI application and router
- `backend/models/schemas.py` - Pydantic models (`InterviewPlan`, API responses)
- `backend/agent/parser.py` - Pydantic AI `ResumeParserAgent`
- `backend/utils/pdf_parser.py` - Utility to extract text from uploaded PDFs

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [FastAPI Upload Files](https://fastapi.tiangolo.com/tutorial/request-files/)
  - Why: Needed for the `/upload` endpoint to handle file uploads securely.
- [Pydantic AI Structured Output](https://ai.pydantic.dev/results/#structured-data)
  - Why: Required for generating the strongly-typed `InterviewPlan`.

### Patterns to Follow

**Naming Conventions:**
- Python files and variables: `snake_case`
- Pydantic Models and Classes: `PascalCase`

**Error Handling:**
- Use FastAPI's `HTTPException` for API errors (e.g., invalid file type).

**Pydantic AI Pattern:**
```python
from pydantic import BaseModel
from pydantic_ai import Agent

class InterviewPlan(BaseModel):
    skills: list[str]
    question_bank: list[str]

agent = Agent('openai:gpt-4o-mini', output_type=InterviewPlan, instructions='Extract skills and create questions based on the resume.')
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

**Tasks:**
- Initialize the backend directory structure.
- Create `requirements.txt` with necessary libraries.
- Set up the environment variables (`.env`).

### Phase 2: Core Implementation

**Tasks:**
- Define Pydantic models in `backend/models/schemas.py` for the expected `InterviewPlan` and the API response.
- Create a utility `backend/utils/pdf_parser.py` to extract text from `UploadFile` (PDF).
- Implement the `ResumeParserAgent` in `backend/agent/parser.py` using Pydantic AI to take resume text and output the `InterviewPlan`.

### Phase 3: Integration

**Tasks:**
- Create the FastAPI application in `backend/api/main.py`.
- Implement the `POST /upload` endpoint.
- Connect the upload endpoint to the PDF parsing utility and the `ResumeParserAgent`.

### Phase 4: Testing & Validation

**Tasks:**
- Validate the endpoint using `curl` or a python script.
- Ensure the parsed resume text correctly generates the `InterviewPlan` struct and is returned by the endpoint.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE backend/requirements.txt

- **IMPLEMENT**: Add `fastapi`, `uvicorn`, `python-multipart`, `pydantic-ai`, `pypdf`, `python-dotenv`, `ruff`.
- **VALIDATE**: `mkdir -p backend && pip install -r backend/requirements.txt`

### CREATE backend/models/schemas.py

- **IMPLEMENT**: Define `InterviewPlan` model with fields: `candidate_name` (str), `extracted_skills` (list of strings), and `question_bank` (list of strings). Define an `UploadResponse` model with fields `session_id` (str) and `plan_summary` (InterviewPlan).
- **IMPORTS**: `from pydantic import BaseModel, Field`
- **VALIDATE**: `python -c "from backend.models.schemas import InterviewPlan"`

### CREATE backend/utils/pdf_parser.py

- **IMPLEMENT**: Create an async function `extract_text_from_pdf(file_bytes: bytes) -> str` using `pypdf` to read text from a PDF.
- **IMPORTS**: `import io`, `from pypdf import PdfReader`
- **GOTCHA**: Ensure robust error handling if the PDF is malformed. If text is empty, raise a ValueError.
- **VALIDATE**: Create a dummy PDF and test the function locally (or ensure syntax is correct).

### CREATE backend/agent/parser.py

- **IMPLEMENT**: Initialize a Pydantic AI `Agent`. Set `output_type=InterviewPlan`. Write instructions telling the agent to act as an expert technical recruiter, extract the candidate's name and core skills, and formulate 3-5 personalized interview questions based on their experience.
- **IMPORTS**: `from pydantic_ai import Agent`, `from backend.models.schemas import InterviewPlan`
- **GOTCHA**: Use a fast model like `'openai:gpt-4o-mini'` or `'google-gla:gemini-1.5-flash'`. Ensure `OPENAI_API_KEY` or appropriate API key is expected in the environment.
- **VALIDATE**: `python -c "from backend.agent.parser import agent"`

### CREATE backend/api/main.py

- **IMPLEMENT**: Initialize FastAPI app. Implement `POST /upload` endpoint accepting `file: UploadFile = File(...)`. In the endpoint: read file bytes, extract text using `pdf_parser`, run the `ResumeParserAgent` (`agent.run_sync(text)`), and return the `session_id` (uuid) and `plan_summary` containing the struct.
- **IMPORTS**: `from fastapi import FastAPI, UploadFile, File, HTTPException`, `import uuid`, `from backend.agent.parser import agent`, `from backend.utils.pdf_parser import extract_text_from_pdf`, `from backend.models.schemas import UploadResponse`
- **VALIDATE**: `uvicorn backend.api.main:app --reload` (starts without error).

---

## TESTING STRATEGY

### Integration Tests
Test the `/upload` endpoint by sending a real PDF resume and verifying the JSON response conforms to the `UploadResponse` and that the inner `InterviewPlan` contains valid skills and questions.

### Edge Cases
- User uploads a non-PDF file. (Should return 400 Bad Request)
- User uploads an empty PDF or image-based PDF where text extraction fails. (Should handle gracefully)
- LLM API timeout or failure.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

`cd backend && ruff check .`

### Level 2: Manual Validation

1. Start the server:
`cd backend && uvicorn api.main:app --host 0.0.0.0 --port 8000`

2. In another terminal, create a dummy PDF and test the upload:
`curl -X POST -F "file=@test_resume.pdf" http://localhost:8000/upload`

Verify the output contains a valid `session_id` and parsed `plan_summary`.

---

## ACCEPTANCE CRITERIA

- [ ] `backend` directory structure is created.
- [ ] `/upload` endpoint successfully accepts a PDF file.
- [ ] Text is successfully extracted from the PDF.
- [ ] `ResumeParserAgent` processes the text and outputs a structured `InterviewPlan`.
- [ ] Endpoint returns a JSON response containing a unique `session_id` and the generated plan.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] Manual testing confirms `/upload` endpoint works with a PDF
- [ ] Acceptance criteria all met

---

## NOTES

- The MVP requires transient state; for now, generating a `uuid` as `session_id` per upload is sufficient. Storing the session state long-term is outside the scope of Phase 1.
