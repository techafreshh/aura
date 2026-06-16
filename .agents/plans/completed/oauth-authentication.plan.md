# Plan: OAuth Authentication (Google + GitHub)

## Overview

Add OAuth authentication with Google and GitHub providers, role-based access control (Admin + Candidate), and migrate from in-memory storage to SQLite.

## Current State

- **Zero auth** — all endpoints are public
- Session IDs (UUIDs) are the only identifier, generated at upload time
- Plans and reports stored in in-memory dicts (`backend/api/main.py:53-54`)
- Worker fetches plans via unauthenticated HTTP `GET /plan/{session_id}`
- Frontend uses axios with no auth headers

## Approach: Authlib + JWT + SQLite

| Component | Choice | Rationale |
|-----------|--------|-----------|
| OAuth library | **Authlib** | Most battle-tested for FastAPI, handles PKCE, token refresh |
| Auth tokens | **JWT (PyJWT)** | Stateless, works across frontend/backend/worker |
| Database | **SQLite via SQLAlchemy async** | Zero new infrastructure, async-compatible via aiosqlite |

### Why SQLite over Postgres

The app's write pattern (one write per interview session) is well within SQLite's capabilities. No new Docker container needed. SQLAlchemy's ORM makes Postgres migration a one-line engine change later if needed.

## Environment Variables (New)

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | Secret key for signing JWTs |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret |
| `ADMIN_EMAIL` | Email address that gets admin role (your email) |
| `WORKER_API_KEY` | Shared secret for worker-to-backend auth |

## Implementation Phases

### Phase 1 — Database Layer

1. Add to `backend/pyproject.toml`:
   ```
   "sqlalchemy[asyncio]>=2.0",
   "aiosqlite>=0.20",
   "authlib>=1.3",
   "PyJWT>=2.8",
   ```

2. Create `backend/db/__init__.py`

3. Create `backend/db/database.py` — async SQLAlchemy engine:
   - Engine: `sqlite+aiosqlite:///./data/aura.db`
   - `async_sessionmaker` for request-scoped sessions
   - `init_db()` function to create tables on startup
   - `get_db()` async generator for FastAPI dependency injection

4. Create `backend/db/models.py` — SQLAlchemy models:
   ```python
   class User(Base):
       __tablename__ = "users"
       id: str  # UUID primary key
       email: str  # unique, indexed
       name: str
       avatar_url: str  # nullable, from OAuth provider
       provider: str  # "google" | "github"
       provider_id: str  # provider's user ID
       role: str  # "admin" | "candidate"
       created_at: datetime
       last_login_at: datetime

   class InterviewSession(Base):
       __tablename__ = "interview_sessions"
       id: str  # UUID (was session_id)
       user_id: str  # FK -> users.id, indexed
       candidate_name: str
       plan_json: Text  # serialized InterviewPlan
       report_json: Text  # nullable, serialized FinalReport
       transcript_json: Text  # nullable
       status: str  # "pending" | "in_progress" | "completed"
       created_at: datetime
       completed_at: datetime  # nullable
   ```

5. Create `backend/db/crud.py` — async helper functions:
   - `upsert_user(email, name, provider, provider_id, avatar_url) -> User`
   - `get_user_by_id(user_id) -> User | None`
   - `create_session(user_id, candidate_name, plan_json) -> InterviewSession`
   - `get_session(session_id) -> InterviewSession | None`
   - `update_session_report(session_id, report_json, status)`
   - `update_session_transcript(session_id, transcript_json)`
   - `list_user_sessions(user_id, limit, offset) -> list[InterviewSession]`
   - `list_all_sessions(limit, offset, status) -> list[InterviewSession]`

6. Add startup lifecycle to `backend/api/main.py`:
   ```python
   @app.on_event("startup")
   async def startup():
       await init_db()
   ```

### Phase 2 — OAuth + JWT

7. Create `backend/api/auth.py` with endpoints:
   - `GET /auth/{provider}` — redirects to Google/GitHub consent screen
     - Providers: `"google"` and `"github"`
     - Uses Authlib's `OAuthClient` registered per provider
     - Generates state token for CSRF protection
   - `GET /auth/{provider}/callback` — exchanges code for token:
     - Fetches user profile from provider (email, name, avatar)
     - Calls `upsert_user()` to create or update DB record
     - Assigns role: `role = "admin" if user.email == ADMIN_EMAIL else "candidate"`
     - Generates JWT with payload: `{sub: user_id, email, role, name, exp}`
     - Returns JWT in JSON response `{token, user: {id, email, name, role, avatar_url}}`
   - `GET /auth/me` — returns current user from JWT
   - `POST /auth/logout` — client-side token clear (server is stateless)

8. Create `backend/api/deps.py` — FastAPI dependencies:
   ```python
   async def get_current_user(request: Request) -> User:
       """Extract and validate JWT from Authorization header.
       Also accepts WORKER_API_KEY for internal service calls."""
       auth_header = request.headers.get("Authorization")
       if not auth_header:
           raise HTTPException(401, "Not authenticated")
       
       token = auth_header.replace("Bearer ", "")
       
       # Check if it's the worker API key
       if token == WORKER_API_KEY:
           return None  # Worker has special privileges
       
       try:
           payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
           user = await get_user_by_id(payload["sub"])
           if not user:
               raise HTTPException(401, "User not found")
           return user
       except jwt.ExpiredSignatureError:
           raise HTTPException(401, "Token expired")
       except jwt.InvalidTokenError:
           raise HTTPException(401, "Invalid token")

   def require_admin(user: User):
       if user.role != "admin":
           raise HTTPException(403, "Admin access required")
   ```

9. Configure Authlib OAuth clients:
   ```python
   # backend/api/auth.py
   from authlib.integrations.starlette_client import OAuth

   oauth = OAuth()
   oauth.register(
       name="google",
       client_id=GOOGLE_CLIENT_ID,
       client_secret=GOOGLE_CLIENT_SECRET,
       server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
       client_kwargs={"scope": "openid email profile"},
   )
   oauth.register(
       name="github",
       client_id=GITHUB_CLIENT_ID,
       client_secret=GITHUB_CLIENT_SECRET,
       access_token_url="https://github.com/login/oauth/access_token",
       authorize_url="https://github.com/login/oauth/authorize",
       api_base_url="https://api.github.com/",
       client_kwargs={"scope": "user:email"},
   )
   ```

### Phase 3 — Migrate Endpoints

10. Refactor `POST /upload`:
    - Add `user: User = Depends(get_current_user)`
    - Create `InterviewSession` DB row instead of storing in `plans` dict
    - Set `session.user_id = user.id`, `session.status = "pending"`

11. Refactor `GET /plan/{session_id}`:
    - Fetch from DB instead of `plans` dict
    - Auth optional — worker uses `WORKER_API_KEY`
    - Response includes `user_id` and `user_email` (for Langfuse tracing)

12. Refactor `POST /report/{session_id}`:
    - Add `@limiter.limit("30/hour")`
    - Accept worker auth via `WORKER_API_KEY`
    - Write to `InterviewSession.report_json` column
    - Update `session.status = "completed"`, `session.completed_at = now()`

13. Refactor `GET /report/{session_id}`:
    - Add `Depends(get_current_user)`
    - Verify `user.id == session.user_id` or `user.role == "admin"`

14. Refactor `POST /transcript/{session_id}`:
    - Write to `InterviewSession.transcript_json` column

15. Refactor `GET /download/{session_id}/{file_type}`:
    - Add auth check — same logic as report endpoint

16. Keep `GET /health` public (no auth)

17. Remove in-memory `plans` and `reports` dicts

### Phase 4 — Worker Auth

18. Worker sends `Authorization: Bearer <WORKER_API_KEY>` header when calling:
    - `GET /plan/{session_id}` (to fetch interview plan)
    - `POST /report/{session_id}` (to save report)
    - `POST /transcript/{session_id}` (to save transcript)

19. Update `worker.py` `generate_and_save_report()`:
    ```python
    headers = {"Authorization": f"Bearer {os.getenv('WORKER_API_KEY')}"}
    async with httpx.AsyncClient() as client:
        await client.post(f"{backend_url}/report/{session_id}", json=..., headers=headers)
        await client.post(f"{backend_url}/transcript/{session_id}", json=..., headers=headers)
    ```

20. Update `entrypoint()` plan fetch:
    ```python
    headers = {"Authorization": f"Bearer {os.getenv('WORKER_API_KEY')}"}
    response = await client.get(f"{backend_url}/plan/{session_id}", headers=headers)
    ```

### Phase 5 — Frontend

21. Create `frontend/src/contexts/AuthContext.tsx`:
    - Stores `{user, token, login, logout, loading}` in React context
    - On mount, checks localStorage for existing JWT, validates via `GET /auth/me`
    - `login(provider)` redirects to `/auth/google` or `/auth/github`
    - `logout()` clears token from localStorage and resets state

22. Create `frontend/src/pages/AuthCallback.tsx`:
    - Handles OAuth callback redirect
    - Extracts token from URL params or response
    - Stores token in localStorage, redirects to `/interview` or `/admin`

23. Create `frontend/src/components/auth/ProtectedRoute.tsx`:
    - Wraps routes that need auth
    - Redirects to login if not authenticated
    - `requireAdmin` prop checks `user.role === "admin"`

24. Update `frontend/src/App.tsx` routing:
    ```tsx
    <Route path="/" element={<Landing />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/interview" element={<ProtectedRoute><InterviewFlow /></ProtectedRoute>} />
    <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
    <Route path="/my-interviews" element={<ProtectedRoute><MyInterviews /></ProtectedRoute>} />
    ```

25. Update `frontend/src/api/client.ts` — axios interceptor:
    ```typescript
    api.interceptors.request.use((config) => {
      const token = localStorage.getItem("aura_token");
      if (token) config.headers.Authorization = `Bearer ${token}`;
      return config;
    });
    ```

26. Add login buttons to Landing page and InterviewFlow page
    - Show "Sign in with Google" and "Sign in with GitHub" buttons
    - Hide upload/join flow until authenticated
    - Show user avatar + name in nav bar when logged in

### Phase 6 — CORS & Security

27. Fix CORS — only allow localhost in dev:
    ```python
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        domain = os.getenv("DOMAIN")
        if not domain:
            raise RuntimeError("DOMAIN env var required in production")
        origins = [domain]
    else:
        origins = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
    ```

28. Add `SameSite=Lax` cookie option for JWT (optional enhancement)

## Migration Path

1. Add DB models and init code — no breaking changes
2. Run `uv run python -c "from db.database import init_db; import asyncio; asyncio.run(init_db())"` to create tables
3. Add OAuth endpoints — no breaking changes
4. Gradually migrate endpoints to use DB instead of in-memory dicts
5. Once all endpoints migrated, remove in-memory dicts
6. Worker auth can be added last (low risk)

## Files to Create/Modify

**New files:**
- `backend/db/__init__.py`
- `backend/db/database.py`
- `backend/db/models.py`
- `backend/db/crud.py`
- `backend/api/auth.py`
- `backend/api/deps.py`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/pages/AuthCallback.tsx`
- `frontend/src/components/auth/ProtectedRoute.tsx`

**Modified files:**
- `backend/pyproject.toml` (new dependencies)
- `backend/api/main.py` (migrate endpoints, add CORS fix)
- `backend/agent/worker.py` (add auth headers)
- `frontend/src/App.tsx` (new routes)
- `frontend/src/api/client.ts` (auth interceptor)
- `frontend/src/pages/Landing.tsx` (login buttons)
- `frontend/src/pages/InterviewFlow.tsx` (auth gate)
- `.env.example` (new variables)

## Open Questions

1. Should candidates be required to log in before uploading a resume, or allow anonymous uploads linked post-hoc?
2. Should OAuth callback URLs be configured for both localhost dev and production?
3. Should the admin be able to view sessions as a specific candidate (impersonation)?
