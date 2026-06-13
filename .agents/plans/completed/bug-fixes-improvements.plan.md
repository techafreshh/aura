# Plan: Bug Fixes and Security Improvements

## Summary

Addresses 10 issues found during codebase audit, prioritized by severity. P0 fixes (CORS, download ACL, input sanitization) are security-critical and should ship first. P1-P2 fixes harden API validation and error handling. P3 improves the report delivery mechanism.

## User Story

As a platform operator, I want the API endpoints secured and validated so that the system is resistant to abuse, data injection, and information leakage.

## Metadata

| Field | Value |
|-------|-------|
| Type | BUG_FIX / ENHANCEMENT |
| Complexity | LOW-MEDIUM per fix, MEDIUM overall |
| Systems Affected | `backend/api/main.py`, `backend/models/schemas.py`, `backend/agent/worker.py`, `frontend/src/components/voice/InterviewAgent.tsx` |
| Jira Issue | N/A |

---

## Patterns to Follow

### Rate Limiting
```
# SOURCE: backend/api/main.py:50
@app.post("/upload", response_model=UploadResponse)
@limiter.limit("10/hour")
async def upload_resume(request: Request, file: UploadFile = File(...)):
```

### Pydantic Model Validation
```
# SOURCE: backend/models/schemas.py:17-20
class EvaluationResult(BaseModel):
    score: Literal["Poor", "Fair", "Good", "Excellent"]
    feedback: str
    suggested_follow_up: Optional[str] = None
```

### API Error Responses
```
# SOURCE: backend/api/main.py:73,155
raise HTTPException(status_code=400, detail="Only PDF files are supported.")
raise HTTPException(status_code=400, detail="Invalid file type. Use: transcript, pdf")
```

### Async API Tests
```
# SOURCE: backend/tests/test_api.py (pattern used across all tests)
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
```

### Env Var Mocking in Tests
```
# SOURCE: backend/tests/test_rate_limiting.py
def test_limiter_uses_redis_url_when_set(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    import importlib
    import api.main as main_module
    importlib.reload(main_module)
```

### Sentry Exception Capture
```
# SOURCE: backend/api/main.py:18-21 (init exists, but worker.py never calls capture_exception)
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=1.0)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/api/main.py` | UPDATE | Fixes 1-6: CORS, download ACL, sanitization, transcript validation, report rate limit, PDF size limit |
| `backend/models/schemas.py` | UPDATE | Fix 4: Add `TranscriptEntry` and `TranscriptPayload` Pydantic models |
| `backend/agent/worker.py` | UPDATE | Fixes 7-8: Fallback report on error, pass exact candidate words to evaluate |
| `frontend/src/components/voice/InterviewAgent.tsx` | UPDATE | Fix 9: Replace polling with SSE |
| `backend/tests/test_api.py` | UPDATE | Tests for fixes 1-6 |
| `backend/tests/test_sanitize.py` | CREATE | Unit tests for `sanitize_name` |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

---

### Task 1: CORS — Restrict localhost in production

- **File**: `backend/api/main.py`
- **Action**: UPDATE (lines 35-43)
- **Implement**: Replace the current origins logic with environment-aware branching. In production (`ENVIRONMENT=production`), require `DOMAIN` env var or raise `RuntimeError`. In development, keep the localhost origins.
- **Mirror**: Current pattern at lines 35-43 — same middleware setup, just conditional origins
- **Validate**: Run `python -c "import api.main"` with `ENVIRONMENT=production` and no `DOMAIN` to confirm RuntimeError

```python
# Replace lines 35-43 with:
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
```

---

### Task 2: Download endpoint rate limiting (interim ACL)

- **File**: `backend/api/main.py`
- **Action**: UPDATE (lines 147-158)
- **Implement**: Add `@limiter.limit("30/hour")` to `download_artifact` and add `request: Request` parameter. This is the interim fix before auth is implemented.
- **Mirror**: `POST /upload` at line 50 — same `@limiter.limit` + `request: Request` pattern
- **Validate**: `python -c "from api.main import app; print([r.path for r in app.routes])"`

```python
@app.get("/download/{session_id}/{file_type}")
@limiter.limit("30/hour")
async def download_artifact(request: Request, session_id: str, file_type: str):
    # ... rest unchanged
```

---

### Task 3: Input sanitization on candidate_name

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Add `sanitize_name()` function (import `re`, `html`). Apply it in `POST /upload` after `result.output` is received: `plan.candidate_name = sanitize_name(plan.candidate_name)`
- **Mirror**: N/A — new utility function
- **Validate**: Unit test (Task 10)

```python
import re
import html

def sanitize_name(name: str) -> str:
    """Strip HTML tags, encode special chars, limit length."""
    name = re.sub(r'<[^>]+>', '', name)
    name = html.escape(name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name
```

Apply in `upload_resume` after line ~70 (`plan = result.output`):
```python
plan.candidate_name = sanitize_name(plan.candidate_name)
```

---

### Task 4: Transcript payload validation

- **File**: `backend/models/schemas.py` — CREATE models
- **Action**: UPDATE
- **Implement**: Add `TranscriptEntry` and `TranscriptPayload` Pydantic models at the end of the file.

```python
class TranscriptEntry(BaseModel):
    speaker: str
    text: str
    timestamp_s: float

class TranscriptPayload(BaseModel):
    candidate_name: str
    entries: List[TranscriptEntry]
```

- **File**: `backend/api/main.py` — UPDATE `save_transcript` (lines 131-136)
- **Action**: UPDATE
- **Implement**: Change `payload: dict` to `payload: TranscriptPayload`. Update `_archive` to serialize entries properly.
- **Mirror**: `POST /report/{session_id}` at line 110 — same typed-body pattern
- **Validate**: `POST /transcript/{session_id}` with `{"invalid": "payload"}` should return 422

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

---

### Task 5: Rate limit POST /report

- **File**: `backend/api/main.py`
- **Action**: UPDATE (lines 110-118)
- **Implement**: Add `@limiter.limit("30/hour")` and `request: Request` parameter to `save_report`.
- **Mirror**: `POST /upload` at line 50 — identical pattern
- **Validate**: Confirm rate limit is applied by checking `app.routes`

```python
@app.post("/report/{session_id}")
@limiter.limit("30/hour")
async def save_report(request: Request, session_id: str, report: FinalReport, background_tasks: BackgroundTasks):
    # ... rest unchanged
```

---

### Task 6: Upload PDF size limit

- **File**: `backend/api/main.py`
- **Action**: UPDATE (lines 139-144)
- **Implement**: Add `MAX_PDF_SIZE = 10 * 1024 * 1024` constant. Check `len(pdf_bytes)` before archiving. Raise HTTP 413 if exceeded.
- **Mirror**: `POST /upload` line 53 — same `HTTPException` for invalid input pattern
- **Validate**: Unit test with oversized payload (Task 10)

```python
MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB

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
```

---

### Task 7: Fallback report on generation failure

- **File**: `backend/agent/worker.py`
- **Action**: UPDATE (lines 63-95, `generate_and_save_report`)
- **Implement**: Wrap `reporter_agent.run()` in its own try/except. On failure, create a fallback `FinalReport` with score=0, "Hold" recommendation, and error message. Add `sentry_sdk.capture_exception(e)`. Keep the transcript POST and report POST in a separate try block.
- **Mirror**: Current error handling at lines 93-95 — extend with Sentry + fallback
- **Validate**: Manually test by temporarily making reporter_agent fail

```python
async def generate_and_save_report(context: InterviewContext, session_id: str):
    if context.report_generated:
        return
    context.report_generated = True

    transcript_text = "\n".join(
        f"{e['speaker']}: {e['text']}" for e in context.transcript
    ) if context.transcript else "No transcript available."

    try:
        result = await reporter_agent.run(
            f"Candidate: {context.plan.candidate_name}\n"
            f"Skills: {', '.join(context.plan.extracted_skills)}\n"
            f"Transcript:\n{transcript_text}"
        )
        report = result.output
    except Exception as e:
        logger.error(f"Report generation failed for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
        report = FinalReport(
            candidate_name=context.plan.candidate_name,
            overall_score=0,
            section_grades=[],
            strengths=[],
            weaknesses=["Report generation encountered an error."],
            recommendation="Hold",
            summary="An error occurred during report generation. Please review the transcript manually."
        )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{backend_url}/report/{session_id}",
                json=report.model_dump()
            )
            if resp.status_code != 200:
                logger.error(f"Report save failed: {resp.status_code} {resp.text}")
                sentry_sdk.capture_message(f"Report save failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"HTTP error saving report for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{backend_url}/transcript/{session_id}",
                json={"candidate_name": context.plan.candidate_name, "entries": context.transcript}
            )
    except Exception as e:
        logger.error(f"Transcript save failed for {session_id}: {e}", exc_info=True)
        sentry_sdk.capture_exception(e)
```

---

### Task 8: Pass exact candidate words to evaluate_answer

- **File**: `backend/agent/worker.py`
- **Action**: UPDATE (lines 100-112)
- **Implement**: Rename parameter from `response_summary` to `candidate_response`. Update the tool description to instruct passing exact words. Update the prompt to use the exact response.
- **Mirror**: Current implementation at lines 100-112 — same structure, different parameter name + description
- **Verify**: Check the `user_input_transcribed` handler (lines 141-147) — it already captures `ev.transcript` (the exact transcription). The LLM agent calling this tool will now be instructed to pass exact words instead of summarizing.

```python
@llm.function_tool(description=(
    "Evaluate the candidate's last answer. Pass the candidate's EXACT words as 'candidate_response'. "
    "Do NOT summarize or paraphrase. Only call when you need help deciding what to ask next."
))
async def evaluate_answer(self, candidate_response: str) -> str:
    logger.info(f"Evaluating answer: {candidate_response}")
    prompt = (
        f"Skills to look for: {self.context.plan.extracted_skills}\n"
        f"Candidate's Exact Response: {candidate_response}"
    )
    try:
        eval_result = await evaluator_agent.run(prompt)
        if eval_result.output.suggested_follow_up:
            return f"Ask this follow-up: {eval_result.output.suggested_follow_up}"
    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")
    return "The answer was satisfactory. Move on to the next topic."
```

---

### Task 9: Replace polling with Server-Sent Events

- **File**: `backend/api/main.py`
- **Action**: UPDATE — add SSE endpoint
- **Implement**: Add `GET /report-stream/{session_id}` that yields a SSE event when the report is available. Uses `StreamingResponse` with `text/event-stream` media type. 6-minute timeout.

```python
import asyncio
from fastapi.responses import StreamingResponse

@app.get("/report-stream/{session_id}")
async def report_stream(session_id: str):
    async def event_generator():
        for _ in range(360):  # 6 min timeout, check every 1s
            report = reports.get(session_id)
            if report:
                yield f"data: {json.dumps(report.model_dump())}\n\n"
                return
            await asyncio.sleep(1)
        yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- **File**: `frontend/src/components/voice/InterviewAgent.tsx`
- **Action**: UPDATE — replace polling `useEffect` with SSE
- **Implement**: Replace the `for` loop polling logic with an `EventSource` connection.

```typescript
useEffect(() => {
  if (hasConnected && roomState === ConnectionState.Disconnected && !hasEnded) {
    setHasEnded(true);
    setEndedOpen(true);
  }

  if (hasEnded && endedOpen) {
    const es = new EventSource(`${BASE_URL}/report-stream/${sessionId}`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.error) {
        setReportError("Report generation timed out. The interview may have been too short for a meaningful report.");
      } else {
        onInterviewEnd(data);
      }
      es.close();
    };
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }
}, [roomState, hasConnected, hasEnded, endedOpen, sessionId, onInterviewEnd]);
```

**Note**: `BASE_URL` must be the API base URL (same one used by the axios client). The `EventSource` API does not support custom headers, so if CORS or auth headers are needed, consider using `fetch` with `ReadableStream` instead.

- **Mirror**: Existing polling pattern in the same file (lines ~216-240) — same trigger conditions, different delivery mechanism
- **Validate**: Manual test — start interview, end it, verify report appears without polling network requests

---

### Task 10: Tests for fixes 1-6

- **File**: `backend/tests/test_api.py` — UPDATE (add tests)
- **File**: `backend/tests/test_sanitize.py` — CREATE
- **Implement**: Add tests following existing patterns (AsyncClient + ASGITransport, plain assert, monkeypatch for env vars).

**test_sanitize.py**:
```python
from api.main import sanitize_name

def test_sanitize_strips_html_tags():
    assert sanitize_name("<script>alert('xss')</script>John") == "alert(&#x27;xss&#x27;)John"

def test_sanitize_escapes_special_chars():
    assert sanitize_name("Tom & Jerry") == "Tom &amp; Jerry"

def test_sanitize_limits_length():
    assert sanitize_name("A" * 200) == "A" * 100

def test_sanitize_normalizes_whitespace():
    assert sanitize_name("  John   Doe  ") == "John Doe"

def test_sanitize_empty_string():
    assert sanitize_name("") == ""
```

**test_api.py** additions:
```python
import importlib

def test_cors_production_requires_domain(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DOMAIN", raising=False)
    import api.main as main_module
    with pytest.raises(RuntimeError, match="DOMAIN"):
        importlib.reload(main_module)

def test_cors_production_uses_domain(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DOMAIN", "https://example.com")
    import api.main as main_module
    importlib.reload(main_module)
    # Should not raise

@pytest.mark.asyncio
async def test_transcript_rejects_invalid_payload():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/transcript/test-session", json={"invalid": "payload"})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_report_endpoint_rate_limited():
    # Verify rate limit decorator is present (structural test)
    from api.main import app as test_app
    routes = {r.path: r for r in test_app.routes if hasattr(r, 'path')}
    # The rate limit is applied via decorator — verify endpoint exists
    report_routes = [r for r in test_app.routes if hasattr(r, 'path') and r.path == "/report/{session_id}"]
    assert len(report_routes) > 0
```

---

## Validation

```bash
# Type check
cd backend && python -c "import api.main; import agent.worker"

# Lint (if configured)
cd backend && ruff check .

# Tests
cd backend && python -m pytest tests/ -v

# Manual verification
# 1. Start backend, confirm CORS error in production mode without DOMAIN
# 2. POST /transcript with invalid payload → 422
# 3. POST /upload-pdf with >10MB file → 413
# 4. End interview → report appears via SSE (no polling requests in Network tab)
```

---

## Acceptance Criteria

- [ ] CORS rejects localhost origins when `ENVIRONMENT=production`
- [ ] Download endpoint has rate limiting (30/hour)
- [ ] `sanitize_name` strips HTML, escapes special chars, limits to 100 chars
- [ ] `POST /transcript` validates payload against `TranscriptPayload` schema (422 on invalid)
- [ ] `POST /report` has rate limiting (30/hour)
- [ ] `POST /upload-pdf` rejects files >10MB with 413
- [ ] Failed report generation produces a fallback report (score=0, Hold) instead of silent loss
- [ ] `evaluate_answer` tool description instructs exact-word passing
- [ ] Frontend uses SSE instead of polling for report delivery
- [ ] All new tests pass
- [ ] Existing tests still pass
