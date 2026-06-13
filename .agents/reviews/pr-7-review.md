# Code Review: PR #7

## Metadata

| Field | Value |
|-------|-------|
| **Scope** | PR #7 — `fix: harden API security, validation, and report reliability` |
| **PR Number** | 7 |
| **Branch** | `feature/bug-fixes-improvements` |
| **Base** | `main` |
| **Author** | techafreshh |
| **Date** | 2026-06-13 |
| **Gate** | high (default) |
| **Recommendation** | NEEDS WORK |

## Summary

PR #7 introduces security hardening across the API (XSS sanitization, CORS enforcement, PDF size limits, rate limiting, typed transcript payloads), an SSE-based report delivery mechanism replacing frontend polling, and improved worker error handling with Sentry integration and fallback reports. The changes are well-structured and address real security gaps. However, there are several medium-severity issues around SSE robustness, test quality, and an unused import that should be addressed before merging.

## Issues Found

### Critical

None.

### High Priority

None.

### Medium Priority

**1. SSE `event_generator` doesn't check for client disconnect**
`backend/api/main.py:213-222` — The SSE generator polls for up to 2 minutes but never calls `await request.is_disconnected()`. If the client closes the `EventSource`, the generator continues running until timeout, wasting server resources.

```python
# Current
async def event_generator():
    try:
        for _ in range(120):
            report = reports.get(session_id)
            if report:
                yield f"data: {json.dumps(report.model_dump())}\n\n"
                return
            await asyncio.sleep(1)
        yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
    finally:
        _sse_connections[session_id] = max(0, _sse_connections.get(session_id, 1) - 1)
```

**Fix**: Pass `request` into the generator scope and check disconnect:
```python
async def event_generator():
    try:
        for _ in range(120):
            if await request.is_disconnected():
                return
            report = reports.get(session_id)
            if report:
                yield f"data: {json.dumps(report.model_dump())}\n\n"
                return
            await asyncio.sleep(1)
        yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
    finally:
        _sse_connections[session_id] = max(0, _sse_connections.get(session_id, 1) - 1)
```

---

**2. `test_cors_production_*` tests use `importlib.reload` without cleanup**
`backend/tests/test_api.py:75-87` — Both `test_cors_production_requires_domain` and `test_cors_production_uses_domain` reload `api.main`, which reinitializes the `FastAPI` app, `Limiter`, Sentry, and all module-level state. After these tests, `main_module.app` is a new instance without the middleware configured by `add_middleware` (since the failed reload in the first test stops before that call). While `from api.main import app` in other test files retains the old app reference, this is fragile — any test file that switches to `main_module.app` will break.

**Fix**: Add a cleanup fixture that reloads the module back to a known-good state after these tests, or restructure the test to avoid reloading the entire module (e.g., test the CORS logic in isolation).

---

**3. `sanitize_name` regex can be bypassed with unclosed tags**
`backend/api/main.py:63-64` — The regex `<(script|style|iframe|object|embed)[^>]*>.*?</\1>` requires a closing tag. Malformed input like `<script>alert('xss')` (no closing `</script>`) will pass through. While the subsequent `re.sub(r'<[^>]+>', '', name)` strips the opening tag, the script content remains.

```python
# Current behavior:
sanitize_name("<script>alert('xss')John") == "alert('xss')John"  # XSS payload survives
```

**Fix**: Add a fallback that strips content between unclosed dangerous tags, or simply reject names containing `<` entirely:
```python
def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown"
    # Strip dangerous tag pairs (with content)
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
    # Strip unclosed dangerous tags and everything after them
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<[^>]+>', '', name)
    name = html.escape(name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name
```

---

**4. Unused `getReport` import in InterviewAgent.tsx after SSE migration**
`frontend/src/components/voice/InterviewAgent.tsx:12` — The polling code that used `getReport` was replaced with SSE, but the import remains:
```typescript
import { getReport } from "@/api/client";
```
This is now unused and will trigger lint warnings.

**Fix**: Remove the `getReport` import.

---

**5. `test_report_endpoint_rate_limited` is a structural check, not a behavioral test**
`backend/tests/test_api.py:89-93` — This test only verifies that a route with path `/report/{session_id}` exists, which is trivially true. It doesn't verify that rate limiting is actually enforced (e.g., that exceeding the limit returns 429).

```python
async def test_report_endpoint_rate_limited():
    from api.main import app as test_app
    report_routes = [r for r in test_app.routes if hasattr(r, 'path') and r.path == "/report/{session_id}"]
    assert len(report_routes) > 0
```

**Fix**: Either make this a real rate-limit test (send 31 requests and verify 429) or remove it since the existing `test_rate_limiting.py` already covers the rate-limiting mechanism.

---

**6. Pre-existing 3 test failures in `test_transcript.py`**
`backend/tests/test_transcript.py` — Three tests fail on `main` before this PR:
- `test_download_transcript_returns_file` (404 instead of 200)
- `test_download_pdf_returns_file` (404 instead of 200)
- `test_download_invalid_file_type_returns_400` (404 instead of 400)

These tests populate `reports[session_id]` but the endpoint returns 404, suggesting the dict reference is stale. The PR switches to `main_module.reports[session_id]` which is a good defensive improvement, but the root cause is unclear since both approaches should reference the same mutable dict. The PR's implementation report claims "49 passed" which suggests these pass after the PR changes — verify this is actually the case.

### Suggestions

**1. Pre-existing F401 lint error in `test_tracing.py`**
`backend/tests/test_tracing.py:2` — `MagicMock` is imported but unused. Not introduced by this PR, but worth cleaning up.

**2. `evaluate_answer` tool relies on LLM compliance**
`backend/agent/worker.py:121-124` — The new description asks for "EXACT words" and "Do NOT summarize." This is an improvement, but there's no enforcement — the LLM may still summarize. Consider adding a length check or keyword overlap validation if exact quoting is critical.

**3. `_sse_connections` could accumulate entries for completed sessions**
`backend/api/main.py:58` — Session IDs are never removed from `_sse_connections` after all connections close (the value reaches 0 but the key persists). For long-running servers, this dict will grow unbounded.

**Fix**: Delete the key when the count reaches 0:
```python
finally:
    new_count = max(0, _sse_connections.get(session_id, 1) - 1)
    if new_count == 0:
        _sse_connections.pop(session_id, None)
    else:
        _sse_connections[session_id] = new_count
```

## Issue Count

| Severity | Count | Blocks Merge? |
|----------|-------|---------------|
| Critical | 0 | No |
| High | 0 | No |
| Medium | 6 | No |
| Suggestions | 3 | No |

## Validation Results

| Check | Status |
|-------|--------|
| Type Check | PASS (frontend `tsc -b && vite build` succeeded) |
| Lint | FAIL (11 ruff errors: 10 pre-existing E402 in worker.py, 1 pre-existing F401 in test_tracing.py) |
| Tests | FAIL (3 pre-existing failures in test_transcript.py — 34 passed, 3 failed) |

## What's Good

- **Security improvements are substantive**: `sanitize_name`, CORS enforcement, PDF size limits, rate limiting on report/download endpoints, and typed transcript payloads all address real gaps.
- **SSE is a better architecture** than polling for report delivery — reduces latency and server load.
- **Worker error handling is significantly improved**: split try/except blocks, fallback `FinalReport` on generation failure, and Sentry integration ensure the worker degrades gracefully.
- **`evaluate_answer` tool description** is more precise, reducing the chance the LLM summarizes instead of quoting.
- **Test coverage is expanded**: new `test_sanitize.py` with 7 tests, new tests for CORS, transcript validation, and SSE streaming.
- **Module state pattern** (`import api.main as main_module`) is a good defensive practice for tests.

## Recommendation

The PR achieves its security and reliability goals but needs a few fixes before merging:

1. Add `request.is_disconnected()` check to the SSE generator
2. Fix `sanitize_name` to handle unclosed dangerous tags
3. Remove unused `getReport` import from `InterviewAgent.tsx`
4. Verify the 3 pre-existing test failures are actually resolved by the `main_module` pattern change
5. Clean up the `_sse_connections` dict when sessions complete

## Audit Trail

| Artifact | Path |
|----------|------|
| Plan | `.agents/plans/completed/pr7-review-fixes.plan.md` |
| Implementation Report | `.agents/reports/pr7-review-fixes-report.md` |
| This Review | `.agents/reviews/pr-7-review.md` |
