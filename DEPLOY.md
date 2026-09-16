# Deployment Guide

## Prerequisites

- Docker & Docker Compose
- A reverse proxy (Caddy, nginx, etc.) with SSL termination
- LiveKit Cloud account
- OpenRouter API key
- OpenAI API key
- MinIO instance (for report archival) — requires `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, plus `MINIO_SECURE=true` when the endpoint uses `https://` (leave `false` for local `minio:9000` over HTTP)
- **SendByte account** for transactional email (email verification, welcome, password reset) — requires `SENDBYTE_API_KEY`, `SENDBYTE_FROM_EMAIL`
- **OAuth provider accounts (Google + GitHub)** for user authentication (required after PR #10)
- A persistent volume or host path mounted at `backend/data/` for the SQLite database

## Setup

1. Clone the repo and enter the directory:

```bash
git clone <repo-url>
cd AI-Interviewer
```

2. Create your environment file (the root `.env` is what `docker compose` reads via `env_file: .env` — `backend/.env.example` is the reference for backend-only local runs):

```bash
cp .env.example .env
```

3. Fill in all values in `.env` with your API keys and domain.

   **Required auth/identity variables (post PR #10):**
   - `JWT_SECRET` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`. Required in production; the backend will refuse to start without a strong (≥32 chars, not on the known-bad list) value.
   - `OAUTH_SESSION_SECRET` — another independently generated secret used to sign the short-lived OAuth state cookie.
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client (Web application).
   - `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` — from GitHub → Settings → Developer settings → OAuth Apps.
   - `ADMIN_EMAIL` — the operator's email; first login with this address grants the `admin` role.
   - `WORKER_API_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"` and share the same value with the worker deployment. Anyone holding this key can submit reports and transcripts as the worker.
   - `FRONTEND_URL` — public URL of the frontend (e.g. `https://yourdomain.com`). Must match the OAuth app's authorized redirect URIs.
   - `SENDBYTE_API_KEY` — from your SendByte dashboard (use `sk_live_...` in production, `sk_test_...` in sandbox). Without it, sign-up works but no verification/welcome/reset emails are sent.
   - `SENDBYTE_FROM_EMAIL` — a verified sender on your SendByte account, e.g. `Aura <no-reply@yourdomain.com>`.
   - `PUBLIC_API_URL` — optional. Public base URL of the API used in email links; defaults to `{FRONTEND_URL}/api` (matching the frontend nginx proxy). Override only if your proxy layout differs.

   **OAuth callback URLs to register with each provider:**
   - Google: `https://yourdomain.com/api/auth/google/callback`
   - GitHub: `https://yourdomain.com/api/auth/github/callback`

   The provider callback must target the backend through nginx's `/api` proxy. `FRONTEND_URL` is where the backend redirects after it has issued the JWT.

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

> **Heads up on rolling updates (post PR #10 + token hardening):** all previously-open API endpoints now require authentication. Any unupdated client (monitoring probes, e2e tests, internal tooling, curl scripts) that hits `/upload`, `/plan/{id}`, `/token`, `/report/{id}`, `/transcript/{id}`, `/upload-pdf/{id}`, or `/download/{id}/{type}` without an `Authorization: Bearer <jwt>` (or the worker API key) will start receiving `401` (`403` for non-owners on `/token`). Coordinate a restart window if any in-flight interviews are active — the previous in-memory `plans`/`reports` stores were replaced by SQLite, so on-disk interview state on a prior deploy is orphaned until those sessions finish.

## Post-Deployment Verification

After the first deploy with PR #10, verify the auth path end-to-end:

1. **Health check (still public):** `curl https://yourdomain.com/api/health` → `{"status":"healthy"}`
2. **Protected endpoint requires auth:** `curl -i https://yourdomain.com/api/upload` → `401 Not authenticated`
3. **OAuth login flow:** open the frontend, click "Continue with Google" (or GitHub), complete the consent screen, and confirm you land on the interview page with your name/avatar shown.
4. **Admin role:** the email matching `ADMIN_EMAIL` is promoted to `admin` on first login. Confirm via `curl -H "Authorization: Bearer <your-jwt>" https://yourdomain.com/api/auth/me` → `"role": "admin"`.
5. **Worker → backend auth:** the worker logs a successful `POST /report/{id}` and `POST /transcript/{id}` with `Authorization: Bearer $WORKER_API_KEY`. If you see `401` in the worker logs, the keys don't match.
6. **Database created:** `ls -la backend/data/aura.db` (or your mounted volume) — created automatically on first backend startup by the Alembic migrations.
7. **Email + password auth (with SendByte configured):** register via the frontend's sign-up form, confirm the verification email arrives (check spam if using a sandbox key), click the link, then sign in with the new credentials. Registering with an existing OAuth-only email returns a 409 pointing at the provider.
8. **Password reset:** request a reset from "Forgot password?", confirm the email arrives within a minute, and set a new password. Reset links expire after 1 hour and are single-use.
9. **Welcome email:** sign in with a brand-new Google/GitHub account and confirm exactly one welcome email is sent (repeated logins must not re-send it).

## Database

- **Engine:** SQLite via SQLAlchemy async (`aiosqlite`).
- **Location:** `backend/data/aura.db` (gitignored). Mount a persistent volume here.
- **Migrations:** Alembic (`backend/migrations/`), applied automatically at backend startup by the FastAPI lifespan handler in `api/main.py`:
  - DB already tracked by Alembic (`alembic_version` table present) → `upgrade head`.
  - Pre-Alembic DB (tables exist but no `alembic_version` — e.g. a `create_all`-era deploy) → any post-release `users` columns are first added via `ALTER TABLE` (`_add_missing_user_columns` in `db/database.py`), then the live schema is compared against `db/models.py` and stamped at head; a schema still missing columns or tables is NOT stamped — startup fails loudly instead of 500ing later with `no such column`. The `oauth_identities` backfill from earlier deploys still runs for those users.
  - Fresh DB → schema created by the initial migration; the email/password columns are added by the `add_email_password_auth_columns` revision.
  After migrations, `init_db` still runs `create_all` (a no-op on a fully migrated schema), the same missing-column backfill, the OAuth identity backfill, and the column drift guard — it logs in development and raises at startup in production. **If you are upgrading from a pre-PR-#10 deploy with a leftover `aura.db`, it is detected, backfilled, and stamped at head automatically — no manual steps.**
  To change the schema: edit `db/models.py`, then run `cd backend && uv run alembic revision --autogenerate -m "describe the change"`, review the generated file, and commit it together with the model change. Migrations run inside the existing backend container — no extra deploy step.
- **Tables:**
  - `users` — `id`, `email` (unique), `name`, `avatar_url`, `provider` (`google` | `github` | `email`), `provider_id`, `role` (`candidate` | `admin`), `password_hash` (null for OAuth-only accounts), `email_verified`, `verification_token_hash` + `verification_token_expires_at`, `reset_token_hash` + `reset_token_expires_at`, `created_at`, `last_login_at`. Only SHA-256 hashes of email tokens are stored — raw tokens exist solely inside email links.
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
5. `AuthCallback.tsx` reads the fragment, stores the token in `localStorage` as `aura_token`, then calls `history.replaceState` to clear the fragment.
6. Subsequent API calls send `Authorization: Bearer <jwt>` via an axios interceptor; the backend's `get_current_user` decodes the JWT, re-reads `role` from the DB on every request, and rejects with `401` on missing/expired/invalid tokens.
7. The worker authenticates with `Authorization: Bearer $WORKER_API_KEY`; a `_WorkerUser` sentinel is returned so endpoint authorization can grant worker-only write access (`/report`, `/transcript`) without impersonating a real user.

### Cross-Provider Accounts

Google and GitHub identities are linked to the same Aura user only when both providers return the same verified email address. Provider identities are stored separately in `oauth_identities`, so signing in with either provider resolves to the same interview history. Accounts with different emails are not merged automatically.

### Email + Password Flow

1. Sign-up (`POST /auth/register`) hashes the password with bcrypt (cost 12), creates the user with `provider="email"` and `email_verified=false`, and emails a 24-hour verification link (SendByte). The raw token is single-use; only its SHA-256 hash is stored.
2. The link (`GET /auth/verify-email?token=...`) marks the address verified and 302s to `{FRONTEND_URL}/auth/verified?status=success|expired|invalid`.
3. Sign-in (`POST /auth/login`) returns 403 `{"code": "email_not_verified"}` until the address is verified, then issues the same 7-day JWT as OAuth.
4. Password reset: `POST /auth/forgot-password` emails a 1-hour single-use link to `{FRONTEND_URL}/reset-password?token=...`; `POST /auth/reset-password` sets the new password (and verifies the address, since the link click proves mailbox access). OAuth-only accounts are silently skipped.
5. First-time Google/GitHub users receive one welcome email (sent only when the OAuth upsert creates the account).
6. Rate limits: register 5/hour, login 10/hour, resend 3/hour, forgot 3/hour, reset 5/hour, verify 30/hour — keyed on `X-Forwarded-For` like the rest of the API.
