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
- **Worker** — LiveKit VoicePipelineAgent with Pydantic AI reasoning agents
- **AI Models** — GPT-4o-mini (voice), Gemini 2.0 Flash via OpenRouter (reasoning), Deepgram (STT), Cartesia (TTS)

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
| `OPENAI_API_KEY` | LiveKit plugins (STT, LLM, TTS) |
| `LIVEKIT_URL` | LiveKit Cloud WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `DOMAIN` | Production domain (CORS) |
| `MINIO_ENDPOINT` | MinIO endpoint for report archival |
| `MINIO_ACCESS_KEY` | MinIO access key |
| `MINIO_SECRET_KEY` | MinIO secret key |
| `MINIO_BUCKET` | MinIO bucket name |
| `LANGFUSE_PUBLIC_KEY` | Langfuse project public key (optional) |
| `LANGFUSE_SECRET_KEY` | Langfuse project secret key (optional) |
| `LANGFUSE_BASE_URL` | Langfuse instance URL (optional) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload PDF resume, returns interview plan |
| `GET` | `/plan/{session_id}` | Retrieve interview plan |
| `GET` | `/token?session_id=` | Generate LiveKit room token |
| `POST` | `/report/{session_id}` | Save interview report |
| `GET` | `/report/{session_id}` | Retrieve interview report |
| `GET` | `/health` | Health check |

## Testing

```bash
cd backend
uv run pytest
```

## License

Private — All rights reserved.
