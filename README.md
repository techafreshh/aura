# Aura — AI Interviewer

A real-time voice AI application that conducts interactive job interviews. Upload a resume, have a natural voice conversation with an AI interviewer, and receive a structured hiring report.

## How It Works

1. **Upload** — Candidate uploads their resume (PDF)
2. **Interview** — AI conducts a live voice interview via WebRTC, asking personalized questions based on the resume
3. **Report** — A structured hiring report is generated with scores, strengths, weaknesses, and a recommendation

## Architecture

```
┌─────────────┐       ┌─────────────┐       ┌──────────────────┐
│   Frontend  │──API──│   Backend   │       │  LiveKit Cloud   │
│  React/Vite │       │   FastAPI   │       │    (WebRTC)      │
└──────┬──────┘       └──────┬──────┘       └────────┬─────────┘
       │                     │                       │
       │    WebRTC audio     │                       │
       └─────────────────────┼───────────────────────┘
                             │
                      ┌──────┴──────┐
                      │   Worker    │
                      │ LiveKit Agent│
                      └─────────────┘
```

- **Frontend** — React 19, Vite, Tailwind, Shadcn UI, LiveKit Components
- **Backend** — FastAPI (upload, token generation, report storage)

## Two Ways to Interview

**Practice mode (candidates):** upload a resume, optionally paste a job description so the
questions target the role, and run a mock voice interview. You get the report, scores, and feedback.

**Recruiter mode:** create an interview with 2–5 of your own questions (plus optional job
description context), and Aura generates a private invite link. The candidate signs in and
completes a voice interview answering exactly those questions — no resume parsing needed.
When they finish, the recruiter gets the PDF report and the **audio recording** of the
conversation. Monthly interviews per recruiter are capped (`RECRUITER_MONTHLY_LIMIT`) to
control AI spend, and the link itself expires after a validity window the recruiter picks
(24 hours by default, `DEFAULT_INVITE_EXPIRY_HOURS`).
- **Worker** — LiveKit VoicePipelineAgent with Pydantic AI reasoning agents
- **AI Models** — GPT-4o-mini (voice), Gemini 2.0 Flash via OpenRouter (reasoning), Deepgram Nova-3 (STT), Fish Audio S2.1 Pro Free (TTS). Every model is env-configurable — see the Environment Variables table.

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js](https://nodejs.org/) 18+
- API keys: OpenRouter, OpenAI, LiveKit Cloud

### Backend

```bash
cd backend
cp .env.example .env   # fill in your API keys
uv sync
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Worker

```bash
cd backend
uv run python agent/worker.py dev
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Docker Deployment

```bash
cp .env.example .env   # fill in all values
docker compose up -d --build
```

The app is served on `127.0.0.1:3000`. Point a reverse proxy (Caddy/nginx) with SSL at it. See [DEPLOY.md](DEPLOY.md) for full details.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Pydantic AI agents (parser, evaluator, reporter) |
| `REASONING_MODEL` | Model for all three reasoning agents, pydantic-ai format (default: `openrouter:google/gemini-2.0-flash-001`) |
| `PARSER_MODEL` / `EVALUATOR_MODEL` / `REPORTER_MODEL` | Per-agent override of `REASONING_MODEL` (same format; optional) |
| `OPENAI_API_KEY` | LiveKit plugins (STT, LLM, TTS) |
| `LIVEKIT_LLM_MODEL` | Voice-pipeline LLM, the interviewer's conversation model (default: `openai/gpt-4o-mini`). Prefix with `openrouter:` (e.g. `openrouter:google/gemini-2.0-flash-001`) to bill tokens to your OpenRouter credits instead of LiveKit Inference |
| `LIVEKIT_STT_MODEL` | STT model (default: `deepgram/nova-3`). Prefix with `openrouter:` to transcribe via OpenRouter's OpenAI-compatible endpoint (billed to OpenRouter; batch per VAD utterance, no streaming interim results, language auto-detected) |
| `LIVEKIT_TTS_MODEL` | LiveKit Inference TTS model (default: `fishaudio/s2.1-pro-free`) |
| `LIVEKIT_TTS_VOICE` | Fish Audio voice ID used by the realtime interviewer |
| `LIVEKIT_TTS_LANGUAGE` | TTS language (default: `en`) |
| `LIVEKIT_URL` | LiveKit Cloud WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `DOMAIN` | Production domain (CORS) |
| `ENVIRONMENT` | `development` or `production` (default: `development`) |
| `DATABASE_PATH` | SQLite file location (unset default: `/app/data/aura.db` in the container, on the compose volume; `backend/data/aura.db` for local runs) |
| `DATABASE_URL` | Optional server-backed database (e.g. `postgresql+asyncpg://aura_user:pw@postgres:5432/aura`); wins over `DATABASE_PATH` when set. Migrations run at startup; see DEPLOY.md for the SQLite→Postgres cutover |
| `BACKEND_URL` | Worker-to-backend URL (e.g. `http://backend:8000` in compose) |
| `MINIO_ENDPOINT` | MinIO endpoint for report archival |
| `MINIO_ACCESS_KEY` | MinIO access key |
| `MINIO_SECRET_KEY` | MinIO secret key |
| `MINIO_BUCKET` | MinIO bucket name |
| `MINIO_SECURE` | `true` when MinIO uses `https://`, else `false` |
| `JWT_SECRET` | HS256 secret (≥32 chars, required in production) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credentials |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth credentials |
| `ADMIN_EMAIL` | Email promoted to `admin` on first login |
| `WORKER_API_KEY` | Worker-to-backend shared secret |
| `FRONTEND_URL` | Public frontend URL for OAuth redirects |
| `LANGFUSE_PUBLIC_KEY` | Langfuse project public key (optional) |
| `LANGFUSE_SECRET_KEY` | Langfuse project secret key (optional) |
| `LANGFUSE_BASE_URL` | Langfuse instance URL (optional) |
| `SENDBYTE_API_KEY` | SendByte API key (`sk_test_…`/`sk_live_…`) for verification, welcome, and password-reset emails (optional — email flows disabled if unset) |
| `SENDBYTE_FROM_EMAIL` | Verified sender address, e.g. `Aura <no-reply@yourdomain.com>` |
| `PUBLIC_API_URL` | Public base URL of the API for email links; defaults to `{FRONTEND_URL}/api` in production (optional) |
| `RECRUITER_MONTHLY_LIMIT` | Max interviews per recruiter per month (default: 20) |
| `DEFAULT_INVITE_EXPIRY_HOURS` | Default validity window for recruiter invite links (default: 24) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload PDF resume, returns interview plan |
| `GET` | `/plan/{session_id}` | Retrieve interview plan |
| `GET` | `/token?session_id=` | Generate LiveKit room token (owner or admin only) |
| `POST` | `/report/{session_id}` | Save interview report |
| `GET` | `/report/{session_id}` | Retrieve interview report |
| `GET` | `/sessions/mine` | List authenticated user's sessions |
| `GET` | `/admin/sessions` | List all sessions (admin only, supports `?status=` filter) |
| `GET` | `/admin/sessions/{session_id}/detail` | Full session detail with transcript (admin only) |
| `GET` | `/admin/sessions/{session_id}/report` | Session report (admin only) |
| `POST` | `/auth/register` | Create account with email + password (sends verification email) |
| `POST` | `/auth/login` | Sign in with email + password (blocked until email is verified) |
| `GET` | `/auth/verify-email?token=` | Verify an email address (link clicked from email) |
| `POST` | `/auth/resend-verification` | Re-send the verification email |
| `POST` | `/auth/forgot-password` | Send a password-reset link (via SendByte) |
| `POST` | `/auth/reset-password` | Set a new password with a reset token |
| `GET` | `/health` | Health check |
| `POST` | `/auth/role` | Role picker: set candidate/recruiter role |
| `POST` | `/recruiter/invites` | Create interview invite (2–5 questions, optional `expires_in_hours`) |
| `GET` | `/recruiter/invites` | List recruiter's invites + quota usage |
| `GET` | `/recruiter/invites/{id}` | Invite detail with report/transcript |
| `POST` | `/recruiter/invites/{id}/cancel` | Cancel a pending invite |
| `GET` | `/invite/{token}` | Candidate: preview an invite |
| `POST` | `/invite/{token}/start` | Candidate: redeem invite, create session (410 once the link has expired) |
| `POST` | `/audio/{session_id}` | Upload browser-recorded interview audio |
| `GET` | `/download/{session_id}/audio` | Download interview recording |

## Testing

```bash
cd backend
uv run pytest
```

## License

Private — All rights reserved.
