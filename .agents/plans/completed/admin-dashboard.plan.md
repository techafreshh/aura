# Plan: Admin Dashboard

## Overview

Add a recruiter/admin dashboard to view all past interviews, scores, and reports. Leverages the authentication system (Plan 1) and database for persistent session data.

**Depends on**: Plan 1 (OAuth Authentication) for user identity, roles, and database.

## Current State

- Frontend has 2 routes: `/` (Landing) and `/interview` (InterviewFlow)
- No database — plans and reports in memory dicts
- `ReportView` component already renders a full report with score ring, section breakdown, strengths/weaknesses
- Reports archived to MinIO as JSON and PDF
- `FinalReport` schema: `candidate_name`, `overall_score`, `section_grades`, `strengths`, `weaknesses`, `recommendation`, `summary`

## Role Model

- **Admin** (`ADMIN_EMAIL` env var): Can view all interviews across all users
- **Candidate** (default): Can view only their own interviews

## Implementation

### Phase 1 — API Endpoints

**1. `GET /admin/sessions`** — list all sessions (admin only):
```python
@app.get("/admin/sessions")
async def list_sessions(
    user: User = Depends(get_current_user),
    status: Optional[str] = Query(None),  # filter: pending, in_progress, completed
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    require_admin(user)
    sessions = await crud.list_all_sessions(limit=limit, offset=offset, status=status)
    return [SessionSummary.from_db(s) for s in sessions]
```

**2. `GET /sessions/mine`** — list current user's sessions (candidates):
```python
@app.get("/sessions/mine")
async def list_my_sessions(user: User = Depends(get_current_user)):
    sessions = await crud.list_user_sessions(user.id)
    return [SessionSummary.from_db(s) for s in sessions]
```

**3. Response model:**
```python
class SessionSummary(BaseModel):
    session_id: str
    candidate_name: str
    overall_score: Optional[int]
    recommendation: Optional[str]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
```

**4. `GET /admin/sessions/{session_id}/detail`** — full session detail (admin only):
```python
@app.get("/admin/sessions/{session_id}/detail")
async def get_session_detail(session_id: str, user: User = Depends(get_current_user)):
    require_admin(user)
    session = await crud.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "session_id": session.id,
        "candidate_name": session.candidate_name,
        "user_email": session.user_email,
        "plan": InterviewPlan(**json.loads(session.plan_json)) if session.plan_json else None,
        "report": FinalReport(**json.loads(session.report_json)) if session.report_json else None,
        "transcript": json.loads(session.transcript_json) if session.transcript_json else None,
        "status": session.status,
        "created_at": session.created_at,
        "completed_at": session.completed_at,
    }
```

**5. Access control on existing report/transcript endpoints:**
```python
@app.get("/report/{session_id}")
async def get_report(session_id: str, user: User = Depends(get_current_user)):
    session = await crud.get_session(session_id)
    if not session:
        raise HTTPException(404, "Report not found")
    if user.role != "admin" and session.user_id != user.id:
        raise HTTPException(403, "Access denied")
    if not session.report_json:
        raise HTTPException(404, "Report not yet available")
    return FinalReport(**json.loads(session.report_json))
```

### Phase 2 — Frontend Pages

**6. Create `frontend/src/pages/AdminDashboard.tsx`:**

Layout: sortable table of sessions with summary data.

```
Columns:
| Candidate    | Score  | Recommendation | Status    | Date       | Actions |
|--------------|--------|----------------|-----------|------------|---------|
| Dahlia Chen  | 82     | Hire           | Completed | Jun 10     | View    |
| Alex Kumar   | --     | --             | Pending   | Jun 11     | --      |

Features:
- Sort by date, score (click column headers)
- Filter by status: All | Completed | In Progress | Pending
- Search by candidate name
- Click row → navigate to /admin/session/:sessionId
- Stats bar at top: total sessions, avg score, completion rate
```

**7. Create `frontend/src/pages/MyInterviews.tsx`:**

Simplified version for candidates:
```
Columns:
| Date       | Score | Recommendation | Status    | Actions |
|------------|-------|----------------|-----------|---------|
| Jun 10     | 82    | Hire           | Completed | View    |
| Jun 5      | 65    | Hold           | Completed | View    |

Features:
- Only shows the current user's sessions
- Click "View" → navigate to report (reuse ReportView)
- "Start New Interview" button at top
```

**8. Create `frontend/src/pages/SessionDetail.tsx`:**

Full report view for admin:
- Reuses existing `ReportView` component for the report
- Adds transcript viewer below the report (scrollable, speaker-labeled)
- Shows metadata: user email, session timestamps, duration
- Back button to return to dashboard

**9. Update routing in `frontend/src/App.tsx`:**
```tsx
<Routes>
  <Route path="/" element={<Landing />} />
  <Route path="/auth/callback" element={<AuthCallback />} />
  <Route path="/interview" element={<ProtectedRoute><InterviewFlow /></ProtectedRoute>} />
  <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
  <Route path="/admin/session/:sessionId" element={<ProtectedRoute requireAdmin><SessionDetail /></ProtectedRoute>} />
  <Route path="/my-interviews" element={<ProtectedRoute><MyInterviews /></ProtectedRoute>} />
</Routes>
```

**10. Navigation updates:**
- Add "Dashboard" link in nav bar (visible only if `user.role === "admin"`)
- Add "My Interviews" link in nav bar (visible for all authenticated users)
- Landing page shows "View past interviews" link when logged in

### Phase 3 — Data Loading Strategy

**11. For historical data (pre-migration sessions):**

If a session exists in DB but `report_json` is null, fall back to MinIO:
```python
@app.get("/admin/sessions/{session_id}/report")
async def get_session_report(session_id: str, user: User = Depends(get_current_user)):
    require_admin(user)
    session = await crud.get_session(session_id)
    if not session:
        raise HTTPException(404)
    
    if session.report_json:
        return FinalReport(**json.loads(session.report_json))
    
    # Fallback to MinIO
    data = storage.get_artifact(session_id, session.candidate_name, "report.json")
    if data:
        return FinalReport(**json.loads(data))
    
    raise HTTPException(404, "Report not found")
```

## Files to Create

- `frontend/src/pages/AdminDashboard.tsx`
- `frontend/src/pages/MyInterviews.tsx`
- `frontend/src/pages/SessionDetail.tsx`

## Files to Modify

- `backend/api/main.py` — new endpoints, access control on existing endpoints
- `backend/db/crud.py` — list queries (from Plan 1)
- `frontend/src/App.tsx` — new routes
- `frontend/src/pages/Landing.tsx` — nav links
- `frontend/src/api/client.ts` — new API functions

## Styling

Reuse existing design system:
- `aura-report.css` for report views
- `aura-landing.css` card/section patterns for dashboard layout
- Shadcn UI components (Button, Card, Badge, Select, Input) for table UI
- Existing `recPill` function for recommendation badges
