# Deployment Guide

## Prerequisites

- Docker & Docker Compose
- A reverse proxy (Caddy, nginx, etc.) with SSL termination
- LiveKit Cloud account
- OpenRouter API key
- OpenAI API key
- MinIO instance (for report archival) — requires `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
- **OAuth provider accounts (Google + GitHub)** for user authentication (required after PR #10)
- A persistent volume or host path mounted at `backend/data/` for the SQLite database

## Setup

1. Clone the repo and enter the directory:

```bash
git clone <repo-url>
cd AI-Interviewer
```

2. Create your environment file:

```bash
cp .env.example .env
```

3. Fill in all values in `.env` with your API keys and domain.

   **Required auth/identity variables (post PR #10):**
   - `JWT_SECRET` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`. Required in production; the backend will refuse to start without a strong (≥32 chars, not on the known-bad list) value.
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client (Web application).
   - `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` — from GitHub → Settings → Developer settings → OAuth Apps.
   - `ADMIN_EMAIL` — the operator's email; first login with this address grants the `admin` role.
   - `WORKER_API_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"` and share the same value with the worker deployment. Anyone holding this key can submit reports and transcripts as the worker.
   - `FRONTEND_URL` — public URL of the frontend (e.g. `https://yourdomain.com`). Must match the OAuth app's authorized redirect URIs.

   **OAuth callback URLs to register with each provider:**
   - Google: `{FRONTEND_URL}/auth/google/callback` (or configure the redirect to your backend's `/auth/google/callback` per your proxy routing)
   - GitHub: `{FRONTEND_URL}/auth/github/callback`

4. Build and start all services:

```bash
docker compose up -d --build
```

5. Configure your reverse proxy to point at port 3000. Example Caddyfile:

```
yourdomain.com {
    reverse_proxy localhost:3000
}
```

6. Verify the deployment:

```bash
curl https://yourdomain.com/api/health
```

## Updating

```bash
git pull
docker compose up -d --build
```

> **Heads up on rolling updates (post PR #10):** all previously-open API endpoints now require authentication. Any unupdated client (monitoring probes, e2e tests, internal tooling, curl scripts) that hits `/upload`, `/plan/{id}`, `/report/{id}`, `/transcript/{id}`, `/upload-pdf/{id}`, `/download/{id}/{type}`, or `/report-stream/{id}` without an `Authorization: Bearer <jwt>` (or the worker API key) will start receiving `401`. Coordinate a restart window if any in-flight interviews are active — the previous in-memory `plans`/`reports` stores were replaced by SQLite, so on-disk interview state on a prior deploy is orphaned until those sessions finish.

## Post-Deployment Verification

After the first deploy with PR #10, verify the auth path end-to-end:

1. **Health check (still public):** `curl https://yourdomain.com/api/health` → `{"status":"healthy"}`
2. **Protected endpoint requires auth:** `curl -i https://yourdomain.com/api/upload` → `401 Not authenticated`
3. **OAuth login flow:** open the frontend, click "Continue with Google" (or GitHub), complete the consent screen, and confirm you land on the interview page with your name/avatar shown.
4. **Admin role:** the email matching `ADMIN_EMAIL` is promoted to `admin` on first login. Confirm via `curl -H "Authorization: Bearer <your-jwt>" https://yourdomain.com/api/auth/me` → `"role": "admin"`.
5. **Worker → backend auth:** the worker logs a successful `POST /report/{id}` and `POST /transcript/{id}` with `Authorization: Bearer $WORKER_API_KEY`. If you see `401` in the worker logs, the keys don't match.
6. **Database created:** `ls -la backend/data/aura.db` (or your mounted volume) — created on first backend startup via `Base.metadata.create_all`.

## Database

- **Engine:** SQLite via SQLAlchemy async (`aiosqlite`).
- **Location:** `backend/data/aura.db` (gitignored). Mount a persistent volume here.
- **Migrations:** none — schema is created at startup via `Base.metadata.create_all` (`backend/db/database.py`). This is non-destructive: existing tables are left alone, missing tables are added. **If you are upgrading from a pre-PR-#10 deploy with a leftover `aura.db`, review the new tables (`users`, `interview_sessions`) and decide whether to keep or wipe the file.**
- **Tables:**
  - `users` — `id`, `email` (unique), `name`, `avatar_url`, `provider`, `provider_id`, `role` (`candidate` | `admin`), `created_at`, `last_login_at`.
  - `interview_sessions` — `id`, `user_id` (FK), `candidate_name`, `plan_json`, `report_json`, `transcript_json`, `status` (`pending` | `in_progress` | `completed`), `created_at`, `completed_at`.

## Architecture

- **frontend** (nginx) — serves the React SPA and proxies `/api/*` to the backend. Auth-gated routes (`/interview/*`, `/report/*`) are wrapped in `ProtectedRoute` and require a valid JWT in `localStorage`.
- **backend** (FastAPI) — handles uploads, token generation, reports, OAuth callbacks, JWT issuance, and SQLite-backed session storage.
- **worker** (LiveKit agent) — connects to LiveKit Cloud for voice interviews and authenticates to the backend with the `WORKER_API_KEY` shared secret.

The backend and worker are not exposed to the internet. Only the frontend container is reachable (on `127.0.0.1:3000`), and your reverse proxy handles SSL and public access.

### Auth Flow (post PR #10)

1. User clicks "Continue with Google/GitHub" on the landing page.
2. Frontend navigates to `/auth/{provider}` on the backend, which 302s to the provider's consent screen.
3. Provider redirects back to `/auth/{provider}/callback` on the backend; the backend upserts the user into SQLite, issues a 7-day HS256 JWT, and 302s to `{FRONTEND_URL}/auth/callback#token=...&user=...`.
4. The token is delivered in the URL **fragment** (not query string) so it never reaches the server in `Referer` headers or access logs.
5. `AuthCallback.tsx` reads the fragment, stores the token in `localStorage` as `auth_token`, then calls `history.replaceState` to clear the fragment.
6. Subsequent API calls send `Authorization: Bearer <jwt>` via an axios interceptor; the backend's `get_current_user` decodes the JWT, re-reads `role` from the DB on every request, and rejects with `401` on missing/expired/invalid tokens.
7. The worker authenticates with `Authorization: Bearer $WORKER_API_KEY`; a `_WorkerUser` sentinel is returned so endpoint authorization can grant worker-only write access (`/report`, `/transcript`) without impersonating a real user.
