# Plan: PR #7 Review Fixes

## Summary

Harden the API security, validation, and report reliability changes from PR #7 by fixing the issues identified in code review: incomplete XSS sanitization, unprotected SSE endpoint, missing test coverage, and minor code quality issues. All fixes are applied on top of the PR branch before merging.

## User Story

As a developer
I want the security hardening in PR #7 to be complete and correct
So that we can merge with confidence and not introduce new attack surfaces

## Metadata

| Field | Value |
|-------|-------|
| Type | BUG_FIX |
| Complexity | MEDIUM |
| Systems Affected | backend/api, backend/agent, backend/tests |
| Jira Issue | N/A |
| PR | [#7 techafreshh/aura](https://github.com/techafreshh/aura/pull/7) |

---

## Patterns to Follow

### Rate Limiting
```python
# SOURCE: backend/api/main.py:24-30, 67, 99
limiter = Limiter(
    key_func=lambda request: request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or get_remote_address(request),
    storage_uri=os.getenv("REDIS_URL"),
    in_memory_fallback_enabled=True,
)

@app.post("/upload", response_model=UploadResponse)
@limiter.limit("10/hour")
async def upload_resume(request: Request, file: UploadFile = File(...)):
```

### Error Handling (Worker)
```python
# SOURCE: backend/agent/worker.py:39-68
# Errors are logged but never re-raised (runs in shutdown callbacks)
except Exception as e:
    logger.error(f"Error generating/saving report: {e}")
```

### Async Test Client
```python
# SOURCE: backend/tests/test_api.py:8-11
async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
    response = await ac.get("/endpoint")
assert response.status_code == 200
```

### Module-Level State Access in Tests
```python
# SOURCE: backend/tests/test_transcript.py:5-6
import api.main as main_module
from api.main import app
# Use main_module.reports / main_module.plans for mutation
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/api/main.py` | UPDATE | Fix sanitize_name, add SSE rate limiting + connection cap, add imports |
| `backend/models/schemas.py` | UPDATE | Add TranscriptEntry and TranscriptPayload models |
| `backend/agent/worker.py` | UPDATE | Deduplicate backend_url, add sentry capture, split try blocks, fix eval prompt |
| `backend/tests/test_sanitize.py` | CREATE | Tests for sanitize_name |
| `backend/tests/test_api.py` | UPDATE | Add SSE endpoint tests, transcript validation test, CORS tests |
| `backend/tests/test_transcript.py` | UPDATE | Fix module-level state access pattern |
| `frontend/src/components/voice/InterviewAgent.tsx` | UPDATE | Replace polling with SSE |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add TranscriptEntry and TranscriptPayload to schemas

- **File**: `backend/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Add two new Pydantic models after `FinalReport`:
  ```python
  class TranscriptEntry(BaseModel):
      speaker: str
      text: str
      timestamp_s: float

  class TranscriptPayload(BaseModel):
      candidate_name: str
      entries: List[TranscriptEntry]
  ```
- **Validate**: `uv run python -c "from models.schemas import TranscriptPayload"`

### Task 2: Fix sanitize_name to strip dangerous tag content

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Add `import re` and `import html` at top. Add `sanitize_name` function:
  ```python
  def sanitize_name(name: str) -> str:
      if not isinstance(name, str):
          return "Unknown"
      name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
      name = re.sub(r'<[^>]+>', '', name)
      name = html.escape(name)
      name = name[:100]
      name = re.sub(r'\s+', ' ', name).strip()
      return name
  ```
  Apply in `/upload` after getting `result.output`:
  ```python
  plan = result.output
  plan.candidate_name = sanitize_name(plan.candidate_name) if plan.candidate_name else "Unknown"
  plans[session_id] = plan
  ```
- **Mirror**: Existing validation pattern in `/upload` endpoint (file extension check)
- **Validate**: `uv run pytest tests/test_sanitize.py -v`

### Task 3: Enforce CORS env-based origin restriction

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Replace the origins block with:
  ```python
  env = os.getenv("ENVIRONMENT", "development")
  if env == "production":
      domain = os.getenv("DOMAIN")
      if not domain:
          raise RuntimeError("DOMAIN env var is required in production")
      origins = [domain]
  else:
      origins = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
  ```
- **Mirror**: Existing env-var pattern (`os.getenv("SENTRY_DSN")`)
- **Validate**: `uv run pytest tests/test_api.py::test_cors_production_requires_domain -v`

### Task 4: Add PDF size limit to upload-pdf endpoint

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Add `MAX_PDF_SIZE = 10 * 1024 * 1024` at module level. In `/upload-pdf`, add size check before background task:
  ```python
  if len(pdf_bytes) > MAX_PDF_SIZE:
      raise HTTPException(status_code=413, detail="PDF exceeds 10 MB limit")
  ```
- **Validate**: Manual review

### Task 5: Add rate limiting to report and download endpoints

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Add `@limiter.limit("30/hour")` and `request: Request` parameter to:
  - `POST /report/{session_id}`
  - `GET /download/{session_id}/{file_type}`
- **Mirror**: Existing `@limiter.limit` on `/upload` and `/token`
- **Validate**: `uv run pytest tests/test_rate_limiting.py -v`

### Task 6: Add SSE report-stream endpoint with rate limiting and connection cap

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Add `import asyncio` and `from fastapi.responses import StreamingResponse` at top. Add connection tracking dict and endpoint:
  ```python
  _sse_connections: dict[str, int] = {}
  MAX_SSE_PER_SESSION = 3

  @app.get("/report-stream/{session_id}")
  @limiter.limit("10/hour")
  async def report_stream(request: Request, session_id: str):
      current = _sse_connections.get(session_id, 0)
      if current >= MAX_SSE_PER_SESSION:
          raise HTTPException(status_code=429, detail="Too many connections for this session")
      _sse_connections[session_id] = current + 1

      async def event_generator():
          try:
              for _ in range(120):  # 2 min timeout
                  report = reports.get(session_id)
                  if report:
                      yield f"data: {json.dumps(report.model_dump())}\n\n"
                      return
                  await asyncio.sleep(1)
              yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
          finally:
              _sse_connections[session_id] = max(0, _sse_connections.get(session_id, 1) - 1)

      return StreamingResponse(event_generator(), media_type="text/event-stream")
  ```
- **Validate**: `uv run pytest tests/test_api.py::test_report_stream_returns_report -v`

### Task 7: Update transcript endpoint to use typed payload

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Import `TranscriptPayload` from schemas. Change `save_transcript` signature:
  ```python
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
  ```
- **Validate**: `uv run pytest tests/test_transcript.py -v`

### Task 8: Harden worker report generation

- **File**: `backend/agent/worker.py`
- **Action**: UPDATE
- **Implement**:
  1. Import `FinalReport` from schemas and `sentry_sdk`
  2. Extract `backend_url` once at top of `generate_and_save_report`
  3. Split into 3 separate try/except blocks: report generation, report save, transcript save
  4. Add fallback `FinalReport` on generation failure:
     ```python
     except Exception as e:
         logger.error(f"Report generation failed for {session_id}: {e}", exc_info=True)
         sentry_sdk.capture_exception(e)
         report = FinalReport(
             candidate_name=context.plan.candidate_name,
             overall_score=0, section_grades=[], strengths=[],
             weaknesses=["Report generation encountered an error."],
             recommendation="Hold",
             summary="An error occurred during report generation. Please review the transcript manually."
         )
     ```
  5. Add `sentry_sdk.capture_exception(e)` to each except block
  6. Fix `evaluate_answer` tool description to ask for exact words, rename param to `candidate_response`
- **Mirror**: Existing error logging pattern in worker
- **Validate**: `uv run pytest tests/test_worker.py -v`

### Task 9: Replace frontend polling with SSE

- **File**: `frontend/src/components/voice/InterviewAgent.tsx`
- **Action**: UPDATE
- **Implement**: Replace the polling `useEffect` block with SSE:
  ```typescript
  const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const es = new EventSource(`${API_BASE}/report-stream/${sessionId}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.error) {
      setReportError("Report generation timed out...");
    } else {
      onInterviewEnd(data);
    }
    es.close();
  };
  es.onerror = () => { es.close(); };
  return () => es.close();
  ```
- **Validate**: `npm run build`

### Task 10: Create test_sanitize.py

- **File**: `backend/tests/test_sanitize.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from api.main import sanitize_name

  def test_sanitize_strips_script_content():
      assert "<script>" not in sanitize_name("<script>alert('xss')</script>John")
      assert "alert" not in sanitize_name("<script>alert('xss')</script>John")
      assert sanitize_name("<script>alert('xss')</script>John") == "John"

  def test_sanitize_escapes_special_chars():
      assert sanitize_name("Tom & Jerry") == "Tom &amp; Jerry"

  def test_sanitize_limits_length():
      assert sanitize_name("A" * 200) == "A" * 100

  def test_sanitize_normalizes_whitespace():
      assert sanitize_name("  John   Doe  ") == "John Doe"

  def test_sanitize_empty_string():
      assert sanitize_name("") == ""

  def test_sanitize_strips_style_tags():
      assert sanitize_name("<style>body{color:red}</style>Jane") == "Jane"

  def test_sanitize_non_string_returns_unknown():
      assert sanitize_name(None) == "Unknown"
  ```
- **Validate**: `uv run pytest tests/test_sanitize.py -v`

### Task 11: Update test_api.py with new tests

- **File**: `backend/tests/test_api.py`
- **Action**: UPDATE
- **Implement**:
  1. Fix import: `import api.main as main_module` + `from api.main import app` (replace `from api.main import app, plans`)
  2. Use `main_module.plans` instead of `plans` in `test_get_plan_success`
  3. Add CORS production tests:
     ```python
     def test_cors_production_requires_domain(monkeypatch):
         monkeypatch.setenv("ENVIRONMENT", "production")
         monkeypatch.delenv("DOMAIN", raising=False)
         with pytest.raises(RuntimeError, match="DOMAIN"):
             importlib.reload(main_module)

     def test_cors_production_uses_domain(monkeypatch):
         monkeypatch.setenv("ENVIRONMENT", "production")
         monkeypatch.setenv("DOMAIN", "https://example.com")
         importlib.reload(main_module)
     ```
  4. Add transcript validation test:
     ```python
     async def test_transcript_rejects_invalid_payload():
         async with AsyncClient(...) as ac:
             response = await ac.post("/transcript/test-session", json={"invalid": "payload"})
         assert response.status_code == 422
     ```
  5. Add SSE stream test:
     ```python
     async def test_report_stream_returns_report():
         session_id = "stream-test-1"
         mock_report = FinalReport(...)
         main_module.reports[session_id] = mock_report
         async with AsyncClient(...) as ac:
             response = await ac.get(f"/report-stream/{session_id}")
         assert response.status_code == 200
         assert "text/event-stream" in response.headers["content-type"]
         assert "Test User" in response.text
     ```
- **Validate**: `uv run pytest tests/test_api.py -v`

### Task 12: Update test_transcript.py module state pattern

- **File**: `backend/tests/test_transcript.py`
- **Action**: UPDATE
- **Implement**: Replace `from api.main import app, reports` with:
  ```python
  import api.main as main_module
  from api.main import app
  ```
  Replace all `reports[session_id]` with `main_module.reports[session_id]`.
- **Mirror**: Pattern already established in this PR's test_api.py changes
- **Validate**: `uv run pytest tests/test_transcript.py -v`

---

## Validation

```bash
# Run all backend tests
cd backend && uv run pytest -v

# Type check (if configured)
cd backend && uv run ruff check .

# Frontend build
cd frontend && npm run build
```

---

## Acceptance Criteria

- [ ] `sanitize_name` strips script/style tag content (not just tags)
- [ ] `sanitize_name` handles non-string input gracefully
- [ ] SSE endpoint has rate limiting (`10/hour`) and per-session connection cap (3)
- [ ] SSE endpoint accepts `request: Request` for slowapi key extraction
- [ ] SSE timeout reduced from 6 min to 2 min
- [ ] Worker `backend_url` extracted once at function top
- [ ] Worker has fallback FinalReport on generation failure
- [ ] Worker calls `sentry_sdk.capture_exception` in error paths
- [ ] `/report` and `/download` endpoints are rate-limited
- [ ] Transcript endpoint uses `TranscriptPayload` Pydantic model
- [ ] CORS enforced by environment (production requires DOMAIN)
- [ ] PDF upload has 10MB size limit
- [ ] Frontend uses SSE instead of polling for report delivery
- [ ] `test_sanitize.py` covers tag stripping, escaping, length, whitespace, empty, non-string
- [ ] `test_api.py` covers CORS, transcript validation, SSE stream
- [ ] `test_transcript.py` uses `main_module` import pattern
- [ ] All existing tests still pass
- [ ] Frontend builds without errors
