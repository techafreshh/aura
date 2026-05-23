# Deployment Guide

## Prerequisites

- Docker & Docker Compose
- A reverse proxy (Caddy, nginx, etc.) with SSL termination
- LiveKit Cloud account
- OpenRouter API key
- OpenAI API key

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

## Architecture

- **frontend** (nginx) — serves the React SPA and proxies `/api/*` to the backend
- **backend** (FastAPI) — handles uploads, token generation, reports
- **worker** (LiveKit agent) — connects to LiveKit Cloud for voice interviews

The backend and worker are not exposed to the internet. Only the frontend container is reachable (on `127.0.0.1:3000`), and your reverse proxy handles SSL and public access.
