# AI Interviewer Backend

This is the backend service for the AI Interviewer Agent. it uses FastAPI to provide an API for uploading resumes and Pydantic AI to generate structured interview plans using LLMs via OpenRouter.

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **AI Orchestration**: [Pydantic AI](https://ai.pydantic.dev/)
- **Package Management**: [uv](https://docs.astral.sh/uv/)
- **LLM Provider**: [OpenRouter](https://openrouter.ai/) (Model: `google/gemini-2.0-flash-001`)
- **PDF Parsing**: `pypdf`

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) installed on your machine.
- An [OpenRouter API Key](https://openrouter.ai/keys).

### Installation

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Initialize the environment and install dependencies:
   ```bash
   uv sync
   ```

3. Create a `.env` file and add your OpenRouter API Key:
   ```bash
   echo "OPENROUTER_API_KEY=your_key_here" > .env
   ```

## Running the Server

Start the FastAPI server with auto-reload enabled:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`. You can view the interactive documentation at `http://localhost:8000/docs`.

## API Endpoints

### `POST /upload`
Upload a PDF resume to generate an interview plan.

- **Request**: `multipart/form-data` with a `file` field.
- **Response**:
  ```json
  {
    "session_id": "uuid",
    "plan_summary": {
      "candidate_name": "string",
      "extracted_skills": ["string"],
      "question_bank": ["string"]
    }
  }
  ```

### `GET /health`
Check if the server is healthy.

## Testing

Run the automated test suite using `pytest`:

```bash
# From the backend directory
$env:PYTHONPATH="."
uv run pytest
```

## Project Structure

```
backend/
├── agent/          # Pydantic AI agent definitions
├── api/            # FastAPI routes and app initialization
├── models/         # Pydantic data models (schemas)
├── utils/          # Utility functions (PDF parsing)
├── tests/          # Automated tests
├── .env            # Environment variables (API keys)
└── pyproject.toml  # Project dependencies and metadata
```
