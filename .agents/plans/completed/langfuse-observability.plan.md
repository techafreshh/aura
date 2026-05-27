# Plan: Langfuse Observability Integration

## Summary

Add Langfuse tracing to all LLM calls across both the backend API (parser agent) and the worker (LiveKit voice pipeline + evaluator + reporter agents). Uses Langfuse's native OpenTelemetry integration — LiveKit via `set_tracer_provider()` and Pydantic AI via `Agent.instrument_all()`. Both containers export traces independently to a self-hosted Langfuse instance, linked by session_id for end-to-end interview visibility.

## User Story

As a developer
I want to trace all LLM calls across both containers with Langfuse
So that I can debug quality issues, track costs, and monitor latency per interview session

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | backend API, worker, Docker config |
| Jira Issue | N/A |

---

## Patterns to Follow

### Error Handling (graceful no-op)
```python
# SOURCE: backend/utils/storage.py:25-40
def archive_report(session_id: str, report_dict: dict, pdf_bytes: bytes) -> None:
    """Upload report JSON and PDF to MinIO. Logs errors, never raises."""
    try:
        client = _get_client()
        # ...
    except Exception as e:
        logger.error("Failed to archive report %s: %s", session_id, e)
```

### Test Pattern (mocking external services)
```python
# SOURCE: backend/tests/test_storage.py:27-40
@patch("utils.storage.Minio")
def test_archive_report_calls_put_object(mock_minio_cls):
    mock_client = MagicMock()
    mock_minio_cls.return_value = mock_client
    mock_client.bucket_exists.return_value = True
    # ...
    assert mock_client.put_object.call_count == 2
```

### Agent Test Pattern (TestModel override)
```python
# SOURCE: backend/tests/test_agents.py:8-20
async def test_evaluator_agent():
    test_model = TestModel(custom_output_args={...})
    with evaluator_agent.override(model=test_model):
        result = await evaluator_agent.run("Test prompt")
    assert isinstance(result.output, EvaluationResult)
```

### Env Var Pattern
```bash
# SOURCE: backend/.env.example:1-5
# OpenRouter API Key for Pydantic AI
OPENROUTER_API_KEY=your_openrouter_api_key
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `langfuse` and `opentelemetry-sdk` dependencies |
| `backend/utils/tracing.py` | CREATE | Shared Langfuse setup utility |
| `backend/api/main.py` | UPDATE | Initialize tracing at startup, tag parser calls with session_id |
| `backend/agent/worker.py` | UPDATE | Initialize tracing in entrypoint with session_id, flush on shutdown |
| `backend/.env.example` | UPDATE | Add Langfuse env vars |
| `.env.example` | UPDATE | Add Langfuse env vars |
| `backend/tests/test_tracing.py` | CREATE | Test tracing utility |
| `README.md` | UPDATE | Document Langfuse env vars |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add dependencies

- **File**: `backend/pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `"langfuse>=3.0.0"` and `"opentelemetry-sdk>=1.20.0"` to the `dependencies` list
- **Mirror**: `backend/pyproject.toml:12-14` — follow existing pinning style (`>=x.y.z`)
- **Validate**: `cd backend && uv lock`

### Task 2: Add environment variables

- **File**: `backend/.env.example`
- **Action**: UPDATE
- **Implement**: Append a Langfuse section at the end:
  ```
  # Langfuse (observability — optional, tracing disabled if unset)
  LANGFUSE_PUBLIC_KEY=
  LANGFUSE_SECRET_KEY=
  LANGFUSE_BASE_URL=http://localhost:3001
  ```
- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Append the same Langfuse section
- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Add 3 rows to the Environment Variables table:
  | `LANGFUSE_PUBLIC_KEY` | Langfuse project public key (optional) |
  | `LANGFUSE_SECRET_KEY` | Langfuse project secret key (optional) |
  | `LANGFUSE_BASE_URL` | Langfuse instance URL (optional) |
- **Mirror**: `README.md` env var table format
- **Validate**: Visual inspection

### Task 3: Create tracing utility module

- **File**: `backend/utils/tracing.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import os
  import logging
  from opentelemetry.sdk.trace import TracerProvider

  logger = logging.getLogger("tracing")

  _provider: TracerProvider | None = None


  def setup_langfuse(metadata: dict | None = None) -> TracerProvider | None:
      """Initialize Langfuse as OTel exporter. Returns None if unconfigured. Never raises."""
      global _provider
      if _provider is not None:
          return _provider

      public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
      secret_key = os.getenv("LANGFUSE_SECRET_KEY")
      base_url = os.getenv("LANGFUSE_BASE_URL")

      if not public_key or not secret_key or not base_url:
          logger.info("Langfuse not configured — tracing disabled")
          return None

      try:
          from langfuse import Langfuse
          from pydantic_ai import Agent

          _provider = TracerProvider()

          Langfuse(
              public_key=public_key,
              secret_key=secret_key,
              base_url=base_url,
              tracer_provider=_provider,
              should_export_span=lambda span: True,
          )

          Agent.instrument_all()
          logger.info("Langfuse tracing initialized (host=%s)", base_url)
          return _provider
      except Exception as e:
          logger.error("Failed to initialize Langfuse: %s", e)
          return None
  ```
- **Mirror**: `backend/utils/storage.py:1-10` — module-level logger, try/except, never raises
- **Validate**: `cd backend && uv run python -c "from utils.tracing import setup_langfuse; print(setup_langfuse())"`  (should print `None` without env vars)

### Task 4: Instrument the backend API

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**:
  1. Add import at top: `from utils.tracing import setup_langfuse`
  2. After `app = FastAPI(...)`, add:
     ```python
     setup_langfuse()
     ```
  3. In the `upload_resume` endpoint, wrap the `agent.run()` call with session context:
     ```python
     from langfuse import propagate_attributes

     # Inside upload_resume, after session_id is generated:
     with propagate_attributes(session_id=session_id):
         # (the agent.run() call is already instrumented via Agent.instrument_all())
     ```
     But since `propagate_attributes` may not be available if Langfuse isn't installed, guard it:
     ```python
     try:
         from langfuse import propagate_attributes
         with propagate_attributes(session_id=session_id):
             result = await agent.run(text)
     except ImportError:
         result = await agent.run(text)
     ```
     Actually simpler — since langfuse IS a dependency, just wrap conditionally on whether tracing is active:
     ```python
     from langfuse import propagate_attributes

     # In upload_resume, replace `result = await agent.run(text)` with:
     with propagate_attributes(session_id=session_id):
         result = await agent.run(text)
     ```
- **Mirror**: `backend/api/main.py:45-50` — existing endpoint structure
- **Validate**: `cd backend && uv run pytest tests/test_api.py`

### Task 5: Instrument the worker

- **File**: `backend/agent/worker.py`
- **Action**: UPDATE
- **Implement**:
  1. Add import at top: `from utils.tracing import setup_langfuse`
  2. Add import: `from livekit.agents.telemetry import set_tracer_provider`
  3. In `entrypoint()`, after `session_id = ctx.room.name`, add:
     ```python
     trace_provider = setup_langfuse(metadata={"langfuse.session.id": session_id})
     if trace_provider:
         set_tracer_provider(trace_provider, metadata={"langfuse.session.id": session_id})
     ```
  4. Update the existing `on_shutdown` callback to flush traces:
     ```python
     async def on_shutdown():
         if report_task:
             await report_task
         else:
             await generate_and_save_report(workflow.context, session_id)
         if trace_provider:
             trace_provider.force_flush()
     ```
- **Note**: The `_provider` singleton in `tracing.py` means the first call sets up the provider. Subsequent interview sessions in the same worker process reuse it. The `metadata` passed to `set_tracer_provider` is per-session via LiveKit's API.
- **Mirror**: `backend/agent/worker.py:110-130` — existing entrypoint structure
- **Validate**: `cd backend && uv run pytest tests/test_worker.py`

### Task 6: Add tracing tests

- **File**: `backend/tests/test_tracing.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import pytest
  from unittest.mock import patch, MagicMock


  def test_setup_langfuse_returns_none_when_unconfigured():
      """Tracing gracefully disabled when env vars are missing."""
      with patch.dict("os.environ", {}, clear=True):
          # Reset singleton
          import utils.tracing
          utils.tracing._provider = None
          result = utils.tracing.setup_langfuse()
          assert result is None


  @patch("utils.tracing.Langfuse")
  @patch("utils.tracing.Agent")
  def test_setup_langfuse_initializes_when_configured(mock_agent, mock_langfuse_cls):
      """Tracing initializes when all env vars are present."""
      import utils.tracing
      utils.tracing._provider = None

      env = {
          "LANGFUSE_PUBLIC_KEY": "pk-test",
          "LANGFUSE_SECRET_KEY": "sk-test",
          "LANGFUSE_BASE_URL": "http://localhost:3001",
      }
      with patch.dict("os.environ", env):
          result = utils.tracing.setup_langfuse()

      assert result is not None
      mock_langfuse_cls.assert_called_once()
      mock_agent.instrument_all.assert_called_once()


  def test_setup_langfuse_does_not_raise_on_error():
      """Tracing never crashes the app."""
      import utils.tracing
      utils.tracing._provider = None

      env = {
          "LANGFUSE_PUBLIC_KEY": "pk-test",
          "LANGFUSE_SECRET_KEY": "sk-test",
          "LANGFUSE_BASE_URL": "http://localhost:3001",
      }
      with patch.dict("os.environ", env):
          with patch("utils.tracing.Langfuse", side_effect=Exception("connection refused")):
              result = utils.tracing.setup_langfuse()
      assert result is None
  ```
- **Mirror**: `backend/tests/test_storage.py:27-55` — @patch pattern, assert on calls
- **Validate**: `cd backend && uv run pytest tests/test_tracing.py`

---

## Validation

```bash
cd backend

# Install new deps
uv lock
uv sync

# Type/import check
uv run python -c "from utils.tracing import setup_langfuse; from api.main import app"

# Tests
uv run pytest

# Docker build (both containers)
cd ..
docker compose build
```

---

## Acceptance Criteria

- [ ] All tasks completed
- [ ] `uv lock` succeeds with new dependencies
- [ ] All existing tests pass (`uv run pytest`)
- [ ] New tracing tests pass
- [ ] Tracing gracefully disabled when env vars are unset (no crash)
- [ ] With Langfuse configured: parser trace appears with session_id
- [ ] With Langfuse configured: worker traces appear with session_id (voice LLM + evaluator + reporter)
- [ ] Docker builds succeed for both containers
- [ ] Follows existing error handling pattern (log, never raise)
