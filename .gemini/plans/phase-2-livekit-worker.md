# Feature: phase-2-livekit-worker

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement Phase 2 of the AI Interviewer project: Real-time Voice (LiveKit Worker). This feature establishes the ultra-low latency voice pipeline necessary for conducting the interactive interview. It introduces a LiveKit `VoicePipelineAgent` worker and a `/token` endpoint in the FastAPI backend to allow the frontend to connect to a LiveKit Cloud room.

## User Story

As a candidate
I want to connect to a real-time voice session
So that I can converse naturally with the AI Interviewer with minimal delay.

As a frontend client
I want to retrieve a secure connection token for a specific session ID
So that I can join the LiveKit room.

## Problem Statement

The application currently parses a resume into a structured interview plan using Pydantic AI (Phase 1), but lacks the capability to actually conduct the interview. We need to implement a real-time, two-way voice communication system utilizing LiveKit Cloud and LiveKit Inference.

## Solution Statement

We will integrate the LiveKit Python Agents SDK to create a `VoicePipelineAgent` that runs as a background worker. This agent will connect to LiveKit Cloud rooms, utilize LiveKit Inference (e.g., OpenAI plugin for LLM, Cartesia for TTS, Deepgram for STT), and handle the conversation flow. We will also add a `/token` endpoint to the existing FastAPI application that dispenses short-lived access tokens for specific session IDs.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: `backend/api`, `backend/agent`
**Dependencies**: 
- `livekit-agents`
- `livekit-api` (for token generation)
- `livekit-plugins-openai`
- `livekit-plugins-silero`
- (Optional TTS/STT plugins based on LiveKit Inference defaults)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/api/main.py` (lines 1-35) - Why: Contains the FastAPI application router where the `/token` endpoint needs to be appended.
- `backend/tests/test_api.py` (lines 1-21) - Why: Shows the current testing pattern using `pytest.mark.asyncio` and `httpx.AsyncClient`.

### New Files to Create

- `backend/agent/worker.py` - LiveKit worker script using `VoicePipelineAgent`.
- `backend/tests/test_worker.py` - Unit tests for the new LiveKit worker (Mandatory per LiveKit agent best practices).

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LiveKit Agents Overview](https://docs.livekit.io/agents/overview/)
  - Specific section: Architecture and `VoicePipelineAgent`
  - Why: This is the core framework for the agent. Note: Always use MCP server `livekit-docs` if available to verify the latest API methods.
- [LiveKit Token Generation](https://docs.livekit.io/realtime/server/authenticating-clients/#creating-a-token)
  - Specific section: Python Token Generation (`AccessToken`)
  - Why: Needed for the `/token` FastAPI endpoint.

### Patterns to Follow

**Naming Conventions:**
- Use snake_case for Python variables and functions.
- Class names use PascalCase.

**Error Handling:**
- The FastAPI `/token` endpoint should return a `400 HTTPException` if `session_id` is not provided.

**Testing Pattern:**
- Use `pytest` with `@pytest.mark.asyncio`.
- Per the `livekit-agents` skill, you MUST write tests for the agent behavior in `backend/tests/test_worker.py`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Configure new dependencies required for LiveKit Cloud integration and token generation. Set up the basic environment variables required.

**Tasks:**
- Install LiveKit SDKs using `uv`.
- Add placeholders/documentation for required `.env` variables (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `OPENAI_API_KEY`).

### Phase 2: Core Implementation

Implement the real-time voice worker using LiveKit's `VoicePipelineAgent` and expose the connection token endpoint.

**Tasks:**
- Add `/token` GET endpoint to `backend/api/main.py`.
- Create `backend/agent/worker.py` with an `entrypoint` function.
- Configure `VoicePipelineAgent` with standard STT, LLM, TTS, and VAD plugins.
- Provide a simple system prompt to verify chat/echo functionality.

### Phase 3: Integration

Connect the LiveKit worker CLI runner. Note that running the worker locally typically involves running `python worker.py dev` alongside the FastAPI server.

**Tasks:**
- Add standard CLI execution block (`if __name__ == "__main__": cli.run_app(...)`) to the worker script.

### Phase 4: Testing & Validation

Implement the required test coverage to ensure the token endpoint generates valid JWTs and the worker initializes cleanly.

**Tasks:**
- Add `test_token_generation` to `backend/tests/test_api.py`.
- Add `test_worker_initialization` to `backend/tests/test_worker.py`.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `backend/pyproject.toml`
- **IMPLEMENT**: Add `livekit-api`, `livekit-agents`, `livekit-plugins-openai`, and `livekit-plugins-silero` to the project using `uv add`.
- **GOTCHA**: Ensure `uv add` is run from within the `backend/` directory.
- **VALIDATE**: `cd backend; uv sync`

### ADD `backend/api/main.py`
- **IMPLEMENT**: Add a `GET /token` endpoint. It must accept a `session_id` query parameter.
- **IMPORTS**: `from livekit.api import AccessToken, VideoGrants`
- **IMPLEMENT**: Generate a token using `AccessToken(api_key, api_secret).with_identity("participant").with_name("Candidate").with_grants(VideoGrants(room_join=True, room=session_id)).to_jwt()`
- **GOTCHA**: Use `os.getenv` to fetch credentials and raise a `500 HTTPException` if they are missing.
- **VALIDATE**: `cd backend; uv run pytest tests/test_api.py` (Note: tests will fail until we write them in the next step, just ensure syntax is valid by running `python api/main.py` if needed).

### ADD `backend/tests/test_api.py`
- **IMPLEMENT**: Write `test_get_token_success` testing the new `/token` endpoint using `httpx.AsyncClient`.
- **IMPLEMENT**: Write `test_get_token_missing_params` (if applicable, though FastAPI handles missing query params automatically).
- **GOTCHA**: You may need to mock `os.getenv` or set dummy environment variables during tests to ensure `AccessToken` doesn't crash on missing keys.
- **VALIDATE**: `cd backend; uv run pytest tests/test_api.py`

### CREATE `backend/agent/worker.py`
- **IMPLEMENT**: Create a basic LiveKit agent worker script.
- **IMPORTS**: `from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm`, `from livekit.agents.voice_pipeline import VoicePipelineAgent`, `from livekit.plugins import openai, silero`.
- **IMPLEMENT**: Define an `async def entrypoint(ctx: JobContext):` function.
- **IMPLEMENT**: Inside `entrypoint`, connect to the room: `await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)`.
- **IMPLEMENT**: Initialize `VoicePipelineAgent(vad=silero.VAD.load(), stt=openai.STT(), llm=openai.LLM(), tts=openai.TTS())` (or equivalent plugins based on LiveKit Inference). Start the agent: `agent.start(ctx.room)`.
- **IMPLEMENT**: Add the execution block: `if __name__ == "__main__": cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))`
- **GOTCHA**: Ensure you call `load_dotenv()` at the top of the file.
- **VALIDATE**: `cd backend; uv run python agent/worker.py --help` (Should display LiveKit CLI help without crashing).

### CREATE `backend/tests/test_worker.py`
- **IMPLEMENT**: Write a unit test `test_worker_import` to ensure `backend/agent/worker.py` can be imported without syntax errors.
- **GOTCHA**: Avoid directly invoking the `entrypoint` without a proper LiveKit test mock. Stick to testing imports and configuration setup for now.
- **VALIDATE**: `cd backend; uv run pytest tests/test_worker.py`

---

## TESTING STRATEGY

### Unit Tests

- **API Tests**: Test the `/token` endpoint to ensure it returns a valid JWT string when provided with a `session_id`. Mock environment variables to ensure test isolation.
- **Worker Tests**: Test that the `worker.py` file can be imported and initialized without errors.

### Integration Tests

- *Deferred*: Full integration tests requiring an active LiveKit Cloud connection are deferred to manual validation or future end-to-end test suites.

### Edge Cases

- User requests a token without configuring `LIVEKIT_API_KEY` on the server.
- The `session_id` is empty or invalid.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

`cd backend; uv run ruff check .`

### Level 2: Unit Tests

`cd backend; uv run pytest`

### Level 4: Manual Validation

1. Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `OPENAI_API_KEY` in `backend/.env`.
2. Start the API server: `cd backend; uv run uvicorn api.main:app --reload`
3. Request a token via browser or curl: `curl "http://localhost:8000/token?session_id=test-123"`
4. Start the worker in a separate terminal: `cd backend; uv run python agent/worker.py dev`
5. Connect a frontend LiveKit sandbox (e.g., LiveKit Meet) to verify the AI connects and speaks.

---

## ACCEPTANCE CRITERIA

- [ ] `uv` dependencies are updated with `livekit-api` and `livekit-agents`.
- [ ] `GET /token?session_id=X` successfully returns a valid LiveKit JWT.
- [ ] `/token` endpoint handles missing server credentials gracefully (returns 500).
- [ ] `backend/agent/worker.py` is implemented and can be executed via CLI.
- [ ] `pytest` executes successfully including new API and Worker tests.
- [ ] `ruff` linting passes with zero errors.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Acceptance criteria all met

---

## NOTES

- The `VoicePipelineAgent` defaults to a simple conversational bot. In Phase 3, this worker will need to be integrated with the Pydantic AI `InterviewPlan` generated in Phase 1 (likely by injecting it into the initial ChatContext). For Phase 2, the goal is simply establishing the functional voice connection.