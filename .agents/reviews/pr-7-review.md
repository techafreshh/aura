# Code Review: PR #7 — fix: harden API security, validation, and report reliability

## Metadata

| Field | Value |
|-------|-------|
| **Scope** | PR #7 |
| **PR Number** | 7 |
| **Branch** | feature/bug-fixes-improvements |
| **Base** | main |
| **Author** | techafreshh |
| **Date** | 2026-06-13 |
| **Gate** | high |
| **Recommendation** | NEEDS WORK |

## Summary

This PR adds API security hardening (XSS sanitization, CORS lockdown, rate limiting, input validation), improves worker report reliability with fallback reports and granular error handling, and replaces frontend polling with SSE for report delivery. The changes are well-structured and address real security/reliability gaps. Two high-severity issues need fixing before merge.

## Issues Found

### Critical

None

### High Priority

#### H1 — SSE connection counter race condition (`backend/api/main.py:235-242`)

The `_sse_connections` dict is decremented in the `finally` block of each SSE generator coroutine. When multiple SSE clients for the same session disconnect concurrently, each coroutine reads-then-writes `_sse_connections[session_id]` without synchronization. Two concurrent decrements can both read the same value, causing the counter to drift and never reach zero (leaking the entry) or underflow.

**Current code:**
```python
finally:
    new_count = max(0, _sse_connections.get(session_id, 1) - 1)
    if new_count == 0:
        _sse_connections.pop(session_id, None)
    else:
        _sse_connections[session_id] = new_count
```

**Recommendation:** Use an `asyncio.Lock` keyed per session, or switch to a simpler pattern with `asyncio.Semaphore(MAX_SSE_PER_SESSION)` that handles cleanup atomically. At minimum, wrap the read-modify-write in a lock:

```python
_sse_locks: dict[str, asyncio.Lock] = {}

async def event_generator():
    lock = _sse_locks.setdefault(session_id, asyncio.Lock())
    try:
        # ...yield events...
    finally:
        async with lock:
            new_count = max(0, _sse_connections.get(session_id, 1) - 1)
            if new_count == 0:
                _sse_connections.pop(session_id, None)
                _sse_locks.pop(session_id, None)
            else:
                _sse_connections[session_id] = new_count
```

#### H2 — EventSource has no error handling or reconnection (`frontend/src/components/voice/InterviewAgent.tsx:274-289`)

The current `onerror` handler silently closes the EventSource with no user feedback or retry logic. If the SSE connection drops transiently (network hiccup, proxy timeout), the user sees the "Generating the candidate report…" overlay indefinitely with no timeout and no error message. The previous polling implementation had a 90-second timeout — this SSE version has none.

**Current code:**
```typescript
es.onerror = () => {
  es.close();
};
```

**Recommendation:** Add a client-side timeout (e.g., 120s to match the server) and surface errors to the user:

```typescript
const timeout = setTimeout(() => {
  es.close();
  setReportError("Report generation timed out. The interview may have been too short for a meaningful report.");
}, 120_000);

es.onerror = () => {
  clearTimeout(timeout);
  es.close();
  setReportError("Connection lost. Please try again.");
};

es.onmessage = (e) => {
  clearTimeout(timeout);
  // ...existing handler...
};
```

### Medium Priority

#### M1 — `sanitize_name` HTML-encodes for JSON responses (`backend/api/main.py:62-72`)

`sanitize_name` applies `html.escape()`, converting `&` to `&amp;`, `<` to `&lt;`, etc. This is appropriate if the name is rendered in HTML, but the name travels through JSON (`UploadResponse` → axios → React). The frontend renders it via JSX (`{plan.candidate_name}`), which auto-escapes HTML entities. This means a name like "Tom & Jerry" becomes "Tom &amp; Jerry" in the UI — double-encoded.

**Recommendation:** Strip dangerous HTML tags but skip `html.escape()` since the name is consumed as JSON data, not raw HTML. If the name must be HTML-safe for a specific context, escape at the point of rendering, not at the API boundary:

```python
def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown"
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<[^>]+>', '', name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "Unknown"
```

#### M2 — Report generation guard is not atomic (`backend/agent/worker.py:67-69`)

`context.report_generated` is a plain boolean checked and set non-atomically. If `on_shutdown` fires while `on_participant_left`'s `_finalize` is between the check and the set (requiring an async context switch at the `await`), both paths could generate reports. In practice this is unlikely since `on_shutdown` awaits the report task, but the guard should use `asyncio.Lock` for correctness:

```python
_report_lock = asyncio.Lock()

async def generate_and_save_report(context, session_id):
    async with _report_lock:
        if context.report_generated:
            return
        context.report_generated = True
    # ...generate and save...
```

### Suggestions

#### S1 — Reuse HTTP client for report + transcript saves (`backend/agent/worker.py:82-101`)

Two separate `httpx.AsyncClient()` instances are created for the report POST and transcript POST. These could share a single client:

```python
async with httpx.AsyncClient() as client:
    resp = await client.post(f"{backend_url}/report/{session_id}", json=report.model_dump())
    # ...
    await client.post(f"{backend_url}/transcript/{session_id}", json={...})
```

#### S2 — SSE test only covers pre-populated report (`backend/tests/test_api.py:94-114`)

`test_report_stream_returns_report` sets the report in memory before requesting the SSE stream, so it only tests the "report already exists" path. Add a test that starts the SSE stream first, then sets the report, verifying the polling behavior.

#### S3 — Consider `asyncio.Lock` for `_sse_connections` access during increment too

The initial check+increment at the top of `report_stream` has the same TOCTOU pattern as the decrement. Two requests could both read `current < MAX_SSE_PER_SESSION` and both pass the check.

## Issue Count

| Severity | Count | Blocks Merge? |
|----------|-------|---------------|
| Critical | 0 | No |
| High | 2 | Yes |
| Medium | 2 | No |
| Suggestions | 3 | No |

## Validation Results

| Check | Status |
|-------|--------|
| Type Check (frontend `tsc -b`) | PASS |
| Tests (backend pytest, 48 tests) | PASS |
| Lint (frontend eslint) | PRE-EXISTING FAIL (41 errors, all pre-existing) |
| Lint (backend ruff) | PRE-EXISTING FAIL (E402 import order in worker.py, pre-existing) |

## What's Good

- **Fail-safe report generation** — the fallback `FinalReport` on exception is a solid pattern that prevents the user from seeing a blank screen when the LLM errors out.
- **Separate error handling** for report save vs. transcript save — failures don't cascade.
- **SSE connection limiting** with `MAX_SSE_PER_SESSION` — prevents resource exhaustion.
- **Comprehensive sanitize_name tests** covering script injection, tag stripping, length limits, and edge cases.
- **CORS production lockdown** — fail-fast on missing `DOMAIN` is the right behavior.
- **PDF size validation** before buffering in memory.
- **TranscriptPayload schema** replaces raw `dict` — proper input validation.

## Recommendation

**NEEDS WORK** — Two high-severity issues block merge:
1. Fix the SSE connection counter race condition (H1)
2. Add timeout and error handling to the frontend EventSource (H2)

The medium issues (double-encoding, non-atomic guard) should also be addressed but aren't blocking.

## Audit Trail

| Artifact | Path |
|----------|------|
| This Review | `.agents/reviews/pr-7-review.md` |
