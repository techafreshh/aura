# Decision Log & Implementation Postmortem: bug-fixes-improvements

- **Date**: 2026-06-12
- **Branch**: `feature/bug-fixes-improvements`
- **Report Path**: `.agents/reports/bug-fixes-improvements-report.md`

## 1. Summary of Implementation

Implemented 10 security and reliability fixes across the backend API, worker agent, and frontend. The changes harden the system against data injection (CORS, input sanitization), information leakage (report fallback), abuse (rate limiting on download/report endpoints), and improve reliability (SSE report delivery, transcript payload validation, PDF size limits). All changes maintain backward compatibility with the existing API contract.

## 2. Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **Environment-aware CORS** (`ENVIRONMENT` + `DOMAIN` env vars) | Production CORS must be locked down to a single domain. Development keeps localhost origins for DX. |
| **`sanitize_name()` strips HTML then escapes** | Defense-in-depth: regex removes tags, `html.escape` encodes remaining special chars, length cap at 100 chars, whitespace normalized. Applied only to `candidate_name` since that's the only user-controlled string flowing into storage keys. |
| **Pydantic models for transcript validation** | Replaces raw `dict` with `TranscriptPayload` to get automatic 422 validation from FastAPI. Prevents malformed data from reaching archive logic. |
| **Fallback `FinalReport` on generation failure** | A failed report generation should never silently lose data. Score=0, "Hold" recommendation, and error message ensure the user always gets something. Sentry capture for observability. |
| **SSE instead of polling for report delivery** | Eliminates unnecessary network requests (was polling every 3s for up to 90s). SSE is simpler than WebSocket and natively supported by browsers. |
| **Rate limit 30/hour on download/report** | Interim ACL before auth is implemented. Prevents abuse while keeping limits generous for legitimate use. |
| **10MB PDF size limit** | Prevents storage abuse. 413 status code is standard for payload too large. |
| **Rewrote entire files instead of targeted edits** | The `edit_file` tool failed on exact whitespace matching for this codebase. Using `write_file` for the full file was more reliable. |

## 3. Errors & Roadblocks Encountered

### Error 1: `edit_file` tool fails on exact string matching
```
ERROR: No occurrences of the specified text were found in the file
```
The `edit_file` tool requires byte-perfect whitespace matching. Despite reading the file content and copying it exactly, the tool couldn't find matches in `main.py` and `schemas.py`.

### Error 2: Python package installation fails — disk full
```
ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device
```
Running `pip install slowapi` (and other deps) on the system Python 3.13 failed because the C: drive was out of space.

### Error 3: Test failure — `test_download_transcript_returns_file` returns 404
```
FAILED tests/test_transcript.py::test_download_transcript_returns_file
assert 404 == 200
```
After CORS tests ran `importlib.reload(main_module)`, the module-level `reports` dict was replaced. Tests that imported `reports` at module level via `from api.main import reports` held a stale reference to the old dict. The endpoint looked at the new dict and couldn't find the session.

### Error 4: Module import timeout
```
ERROR: Command timed out after 30000ms
```
Initial `python -c "import api.main"` timed out due to network calls in sentry/langfuse initialization during module import.

## 4. Workarounds & Resolutions

| Roadblock | Resolution |
|-----------|------------|
| `edit_file` failures | Used `write_file` to rewrite entire files. Less surgical but reliable. |
| Disk full on system Python | Discovered existing `.venv` directory with Python 3.11 and all dependencies pre-installed. Used `.venv\Scripts\python.exe` for all subsequent commands. |
| Stale `reports`/`plans` references | Changed `from api.main import reports` to `import api.main as main_module` and accessed dicts via `main_module.reports[...]`. This ensures the reference stays current after module reloads. |
| Module import timeout | Skipped direct import validation. Relied on pytest (which imports the module successfully) as the validation gate. |

## 5. What Went Right & What Went Wrong

### What Went Right
- All 10 plan tasks implemented exactly as specified
- Frontend TypeScript build (`tsc -b && vite build`) passed on first run
- All 46 tests passed after fixes (including 9 new tests)
- Plan was well-structured with clear task boundaries and validation steps
- Fallback report logic and SSE endpoint integrated cleanly without breaking existing patterns

### What Went Wrong
- `edit_file` tool is unreliable for this codebase — full file rewrites were needed for 3 of 6 file changes
- Test isolation issue: `importlib.reload` in CORS tests polluted global state for downstream tests. This is a pre-existing architectural issue in the test suite.
- Disk space issue forced a pivot to the existing venv rather than a clean install
- The plan didn't account for the module-reload side effect on test imports — this was discovered and fixed during validation

## 6. Lessons Learned & Recommendations

1. **Always use `main_module.X` pattern for module-level mutable state in tests** — If tests call `importlib.reload()`, any `from module import mutable_thing` will capture a stale reference. Access through the module attribute instead.

2. **Prefer `write_file` over `edit_file` for bulk changes** — When modifying more than ~10 lines in a file, rewriting the whole file is more reliable than trying to match exact whitespace.

3. **Verify venv exists before pip install** — Check for `.venv` or `venv` directories first. Installing into system Python is wasteful and may fail on constrained environments.

4. **Module-level side effects (sentry init, network calls) make import validation slow** — Consider lazy initialization or guard patterns for SDKs that make network calls on import.

5. **The plan's test isolation assumption was incomplete** — Plans that use `importlib.reload` should specify the impact on shared module state and prescribe the `main_module.X` access pattern.
