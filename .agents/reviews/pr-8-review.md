# Code Review: PR #8

## Metadata

| Field | Value |
|-------|-------|
| **Scope** | PR #8 — feat: 10-minute interview time cap with graceful wrap-up |
| **PR Number** | 8 |
| **Branch** | feature/interview-time-cap |
| **Base** | main |
| **Author** | techafreshh (Techa) |
| **Date** | 2026-06-13 |
| **Gate** | high |
| **Recommendation** | **APPROVE** |

## Summary

This PR adds a 10-minute time cap to interviews with a graceful 2-minute warning at the 8-minute mark. The backend runs an async timer that injects a wrap-up message at 8 minutes and force-disconnects at 10 minutes. The frontend replaces the elapsed counter with a countdown timer and adds warning/critical visual states. The `InterviewContext` dataclass is also extracted into its own module. The implementation is clean and well-structured.

## Issues Found

### Critical
None

### High Priority
None

### Medium Priority

**1. Frontend/backend timer desync — no synchronization mechanism**
`frontend/src/components/voice/InterviewAgent.tsx:84-85` and `backend/agent/worker.py:257-291`

The frontend starts its countdown from 600s when the WebSocket connects (`hasConnected`), while the backend starts its timer when `entrypoint()` runs (before `session.start()`). There's no mechanism to synchronize these timers. If there's any delay in the LiveKit connection handshake, the frontend will show more time remaining than the backend actually has. In the worst case, the frontend could display ~6:00 remaining when the backend force-disconnects at 10 minutes, which would confuse the candidate.

**Recommendation**: Either (a) pass the backend's `start_time` to the frontend via the session metadata or a timestamp in the greeting message, and compute `remaining` from that, or (b) accept the desync as cosmetic-only and add a comment documenting that the frontend timer is approximate.

**2. Frontend timer shows 00:00 while interview continues**
`frontend/src/components/voice/InterviewAgent.tsx:245`

When the frontend countdown reaches 0, the display shows "00:00" but the interview may still be active (the backend hasn't disconnected yet). The `isCritical` flag (`remaining <= 30 && remaining > 0`) becomes `false` at exactly 0, so the pulsing red animation stops and the timer just sits at 00:00 in the default color with no visual feedback.

**Recommendation**: Handle the `remaining === 0` state explicitly — either keep the critical styling active or show a "Time's up" indicator until the disconnect overlay appears.

### Suggestions

**1. Test coverage is minimal**
`backend/tests/test_worker.py:22-32`

The new test (`test_interview_context_wrap_up_field`) only verifies the dataclass field exists and is mutable. There are no tests for the timer logic itself (e.g., verifying wrap-up triggers at the right elapsed time, or that `generate_and_save_report` is idempotent under the lock). The decision doc acknowledges this gap.

**2. `transcript` field lacks type parameters**
`backend/models/context.py:8`

`transcript: list = field(default_factory=list)` — the new module could be more specific: `list[dict[str, Any]]` to match the actual transcript entry structure used in `worker.py`.

**3. Constants inside component body**
`frontend/src/components/voice/InterviewAgent.tsx:83-84`

`TOTAL_SECONDS` and `WARNING_SECONDS` are `const` declarations inside the render function, recreated every render. Move them outside the component for clarity (performance impact is negligible).

## Issue Count

| Severity | Count | Blocks Merge? |
|----------|-------|---------------|
| Critical | 0 | No |
| High | 0 | No |
| Medium | 2 | No (gate=high) |
| Suggestions | 3 | No |

## Validation Results

| Check | Status |
|-------|--------|
| Type Check (tsc --noEmit) | ✅ PASS |
| Python Compile (py_compile) | ✅ PASS |
| Lint | ⚠️ 8 errors in InterviewAgent.tsx — all pre-existing, none introduced by this PR |
| Tests (new) | ✅ PASS |

## What's Good

- **Clean extraction**: Moving `InterviewContext` to `models/context.py` is the right call — keeps the worker focused on orchestration logic.
- **Idempotent report generation**: The `_report_lock` + `report_generated` flag pattern correctly prevents double report generation from the timer path, disconnect path, and shutdown safety net all potentially racing.
- **Graceful degradation**: The soft wrap-up at 8 minutes gives the agent a chance to conclude naturally before the hard cap, rather than abruptly cutting off.
- **Timer cleanup on disconnect**: `timer_task.cancel()` in `on_participant_left` prevents the timer from firing after the candidate leaves.
- **CSS respects `prefers-reduced-motion`**: The timer pulse animation is correctly disabled by the existing reduced-motion media query (defined after the timer styles, with `!important`).

## Recommendation

**APPROVE** — No blocking issues at the `--gate=high` threshold. The two medium-severity items (timer desync, 00:00 edge case) are UX polish, not correctness or safety problems. The core time cap logic is solid and the idempotent report generation is well-handled.

## Audit Trail

| Artifact | Path |
|----------|------|
| Plan | `.agents/plans/completed/interview-time-cap.plan.md` |
| Implementation Report | `.agents/reports/interview-time-cap-report.md` |
| This Review | `.agents/reviews/pr-8-review.md` |
