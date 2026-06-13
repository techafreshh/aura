# Code Review: PR #7 (Re-review)

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

Re-review of PR #7 after updates addressed findings from the first review. The PR now includes SSE client disconnect handling, proper connection locking, unclosed tag stripping in `sanitize_name`, removed unused imports, and a `_report_lock` for thread safety. However, 2 test failures and 1 lint error were introduced by incomplete test updates after `sanitize_name` behavior changed.

## Issues Found

### Critical

None.

### High Priority

**1. `test_sanitize_escapes_special_chars` fails — `html.escape` removed but test not updated**
`backend/tests/test_sanitize.py:11` — The PR removed `html.escape()` from `sanitize_name` (good — names shouldn't be HTML-escaped), but the test still expects `&amp;`:

```python
# Test expects (wrong):
assert sanitize_name("Tom & Jerry") == "Tom &amp; Jerry"
# Actual result:
assert sanitize_name("Tom & Jerry") == "Tom & Jerry"  # correct behavior
```

**Fix**: Update the test:
```python
def test_sanitize_escapes_special_chars():
    assert sanitize_name("Tom & Jerry") == "Tom & Jerry"
```

---

**2. `test_sanitize_empty_string` fails — `sanitize_name` now returns `"Unknown"` for empty input**
`backend/tests/test_sanitize.py:23` — The PR added `return name or "Unknown"` at the end of `sanitize_name`, converting empty strings to `"Unknown"`. The test expects `""`:

```python
# Test expects (wrong):
assert sanitize_name("") == ""
# Actual result:
assert sanitize_name("") == "Unknown"  # due to `return name or "Unknown"`
```

**Fix**: Update the test:
```python
def test_sanitize_empty_string():
    assert sanitize_name("") == "Unknown"
```

### Medium Priority

**3. Unused `import html` in `api/main.py`**
`backend/api/main.py:5` — The `import html` statement is now unused since `html.escape()` was removed from `sanitize_name`. This produces a F401 lint error.

**Fix**: Remove `import html` from line 5.

### Suggestions

None — all previous review suggestions have been addressed.

## Issue Count

| Severity | Count | Blocks Merge? |
|----------|-------|---------------|
| Critical | 0 | No |
| High | 2 | Yes |
| Medium | 1 | No |
| Suggestions | 0 | No |

## Validation Results

| Check | Status |
|-------|--------|
| Type Check | PASS (frontend build succeeded) |
| Lint | FAIL (10 pre-existing E402 in worker.py, 1 new F401 unused `html` in main.py) |
| Tests | FAIL (46 passed, 2 failed — both test/implementation mismatches) |

## What's Good — Improvements Since Last Review

- **SSE client disconnect handling**: `request.is_disconnected()` check added to `event_generator()` — prevents resource waste
- **SSE connection locking**: `_sse_locks` dict with per-session `asyncio.Lock` for thread-safe connection tracking
- **SSE cleanup**: Properly removes entries from `_sse_connections` and `_sse_locks` when count reaches 0
- **`sanitize_name` unclosed tags**: Now strips unclosed dangerous tags (`<script>alert('xss')`) and everything after them
- **Report generation lock**: `_report_lock = asyncio.Lock()` prevents duplicate report generation from concurrent `participant_disconnected` + `on_shutdown` callbacks
- **Unused imports removed**: `getReport` from InterviewAgent.tsx, `MagicMock` from test_tracing.py
- **Frontend SSE robustness**: Added 120s client-side timeout, `onerror` handler with user-facing message, proper cleanup
- **Pre-existing test failures fixed**: All 3 `test_transcript.py` download tests now pass (the `main_module` pattern works)
- **Test coverage**: 48 tests collected (up from 37), including new sanitize, CORS, transcript validation, and SSE tests

## Recommendation

Three small fixes needed:

1. Update `test_sanitize_escapes_special_chars` to expect `"Tom & Jerry"` (no HTML escaping)
2. Update `test_sanitize_empty_string` to expect `"Unknown"` (matches implementation)
3. Remove unused `import html` from `backend/api/main.py`

## Audit Trail

| Artifact | Path |
|----------|------|
| Plan | `.agents/plans/completed/pr7-review-fixes.plan.md` |
| Implementation Report | `.agents/reports/pr7-review-fixes-report.md` |
| Previous Review | `.agents/reviews/pr-7-review.md` |
| This Review | `.agents/reviews/pr-7-review.md` (updated) |
