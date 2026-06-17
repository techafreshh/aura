# Plan: Langfuse Session Tracing Linked to Authenticated Users

## Overview

Enhance Langfuse observability to track interviews per authenticated user — enabling per-user cost dashboards, session history, and interview quality trends.

**Depends on**: Plan 1 (OAuth Authentication) for user identity.

## Current State

Langfuse is already integrated:
- `backend/utils/tracing.py` — `setup_langfuse()` creates `TracerProvider`, calls `Agent.instrument_all()`
- Worker sets `metadata={'langfuse.session.id': session_id}` via `set_tracer_provider` (worker.py:136)
- Parser agent uses `propagate_attributes(session_id=session_id)` (main.py:79)
- `langfuse>=3.0.0` SDK installed

**Gap**: Traces are linked only by `session_id`. No user identity, no candidate name, no score tracking.

## Implementation

### Phase 1 — Pass User Context Through the Stack

**1. Include user metadata in plan response:**

After Plan 1 adds the DB, update `GET /plan/{session_id}` to return user context alongside the plan:
```python
@app.get("/plan/{session_id}")
async def get_plan(session_id: str):
    session = await get_session_from_db(session_id)
    plan = InterviewPlan(**json.loads(session.plan_json))
    return {
        "plan": plan,
        "user_id": session.user_id,
        "user_email": session.user_email,
    }
```

**2. Worker extracts user context and passes to Langfuse:**

In `entrypoint()`, after fetching the plan:
```python
# After fetching plan from backend:
user_id = plan_response.get("user_id", "anonymous")
user_email = plan_response.get("user_email", "unknown")

if _langfuse_provider:
    set_tracer_provider(_langfuse_provider, metadata={
        "langfuse.session.id": session_id,
        "langfuse.user.id": user_id,
    })
```

### Phase 2 — Enrich Traces with Metadata

**3. Wrap the interview session in a root span with user context:**

In `entrypoint()`, after connecting to the room:
```python
from opentelemetry import trace as otel_trace

tracer = otel_trace.get_tracer("aura-interview")

# Create a root span for the entire interview session
with tracer.start_as_current_span("interview_session") as span:
    span.set_attribute("langfuse.session.id", session_id)
    span.set_attribute("langfuse.user.id", user_id)
    span.set_attribute("langfuse.user.email", user_email)
    span.set_attribute("aura.candidate_name", plan.candidate_name)
    span.set_attribute("aura.skills", ",".join(plan.extracted_skills))
    span.set_attribute("aura.question_count", len(plan.question_bank))

    # ... rest of entrypoint (session.start, etc.)
```

**4. Add post-interview completion metadata:**

In `generate_and_save_report()`, after report is generated:
```python
duration = time.time() - context.start_time

tracer = otel_trace.get_tracer("aura-interview")
with tracer.start_as_current_span("interview_completed") as span:
    span.set_attribute("langfuse.session.id", session_id)
    span.set_attribute("langfuse.user.id", user_id)
    span.set_attribute("aura.duration_seconds", round(duration, 1))
    span.set_attribute("aura.overall_score", report.overall_score)
    span.set_attribute("aura.recommendation", report.recommendation)
    span.set_attribute("aura.transcript_entries", len(context.transcript))
    span.set_attribute("aura.section_count", len(report.section_grades))
```

**5. Propagate user context through Pydantic AI agent calls:**

In `POST /upload` (parser agent):
```python
with propagate_attributes(
    session_id=session_id,
    user_id=user.id,
    user_email=user.email,
):
    result = await agent.run(text)
```

### Phase 3 — Worker Context Sharing

**6. Pass `user_id` into `InterviewContext` and `generate_and_save_report`:**

```python
@dataclass
class InterviewContext:
    plan: InterviewPlan
    user_id: str = "anonymous"  # NEW
    current_phase: str = "Intro"
    transcript: list = field(default_factory=list)
    start_time: float = 0.0
    report_generated: bool = False
```

Set it after fetching the plan:
```python
workflow = InterviewWorkflow(plan=plan, session=session, session_id=session_id)
workflow.context.user_id = user_id
```

Pass to `generate_and_save_report`:
```python
await generate_and_save_report(workflow.context, session_id, user_id=workflow.context.user_id)
```

## What This Enables in Langfuse

After implementation, the Langfuse dashboard supports:

| Feature | How |
|---------|-----|
| **Per-user cost tracking** | Filter traces by `langfuse.user.id` |
| **Session timeline** | View all LLM calls within a `langfuse.session.id` |
| **Interview quality trends** | Query `aura.overall_score` across sessions |
| **Cost per interview** | Sum token costs within a session span |
| **User session history** | Filter by user, see all their interviews |
| **Model comparison** | Compare costs/latency across different LLM calls |

## Files to Modify

- `backend/agent/worker.py` — user context in InterviewContext, span attributes, set_tracer_provider metadata
- `backend/api/main.py` — propagate_attributes with user info, plan response includes user metadata
- `backend/utils/tracing.py` — no changes needed (already sets up provider correctly)

## Risk

- **Requires Plan 1**: User identity comes from OAuth. Without auth, `user_id` defaults to "anonymous" which is the current behavior.
- **OpenTelemetry attribute limits**: Langfuse truncates attribute values > 1000 chars. The `aura.skills` attribute (comma-joined list) should stay well under this.
