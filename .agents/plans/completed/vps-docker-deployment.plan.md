# Plan: VPS Docker Deployment (aura.techa.pro)

## Summary

Deploy the AI Interviewer application (FastAPI backend, LiveKit worker, React frontend) to a VPS using Docker Compose, served behind an existing Caddy reverse proxy at `https://aura.techa.pro`. The backend CORS configuration will be made environment-configurable to support the production domain.

## User Story

As a developer
I want to deploy the AI Interviewer to my VPS with Docker Compose behind Caddy
So that candidates can access it at `https://aura.techa.pro`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | backend, frontend, infrastructure |
| Jira Issue | N/A |

---

## Patterns to Follow

### Backend Entry Point
```python
# SOURCE: backend/api/main.py:1-10
app = FastAPI(title="AI Interviewer API")
# Run: uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Worker Entry Point
```python
# SOURCE: backend/agent/worker.py:197-198
if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
# Run: python -m agent.worker start
```

### Environment Variables
```python
# SOURCE: backend/agent/worker.py:60,106
backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")

# SOURCE: backend/api/main.py:76-77
api_key = os.getenv("LIVEKIT_API_KEY")
api_secret = os.getenv("LIVEKIT_API_SECRET")

# SOURCE: backend/agent/evaluator.py (same in parser.py, reporter.py)
# Pydantic AI agents use OPENROUTER_API_KEY implicitly via load_dotenv()
```

### Frontend Env Usage
```typescript
// SOURCE: frontend/src/api/client.ts:3
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// SOURCE: frontend/src/components/voice/InterviewAgent.tsx:490
const serverUrl = import.meta.env.VITE_LIVEKIT_URL;
```

### CORS (needs modification)
```python
# SOURCE: backend/api/main.py:18-24
allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/api/main.py` | UPDATE | Make CORS origins env-configurable |
| `backend/Dockerfile` | CREATE | Containerize FastAPI API server |
| `backend/Dockerfile.worker` | CREATE | Containerize LiveKit worker |
| `frontend/nginx.conf` | CREATE | SPA + API reverse proxy nginx config |
| `frontend/Dockerfile` | CREATE | Multi-stage build + nginx serve |
| `docker-compose.yml` | CREATE | Orchestrate all services |
| `.env.example` | CREATE | Template for users to copy to `.env` |
| `.gitignore` | CREATE | Ensure `.env` and secrets are never committed |
| `DEPLOY.md` | CREATE | Deployment instructions |

---

## Tasks

### Task 1: Make CORS origins configurable

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Replace hardcoded `allow_origins` list with env-var-driven origins. Read `DOMAIN` env var and combine with localhost defaults: `origins = ["http://localhost:5173", "http://localhost:3000"]` then `if os.getenv("DOMAIN"): origins.append(os.getenv("DOMAIN"))`. This way it works in dev (localhost) and prod (whatever domain the user sets).
- **Mirror**: `backend/api/main.py:18-24`
- **Validate**: `cd backend && uv run python -c "from api.main import app; print('OK')"`

### Task 2: Create backend Dockerfile

- **File**: `backend/Dockerfile`
- **Action**: CREATE
- **Implement**:
  - Base: `python:3.11-slim`
  - Install `uv` via pip
  - Workdir `/app`
  - Copy `pyproject.toml` + `uv.lock` first (layer caching)
  - Run `uv sync --frozen --no-dev`
  - Copy source: `api/`, `agent/`, `models/`, `utils/`, `__init__.py`
  - Expose 8000
  - CMD: `uv run uvicorn api.main:app --host 0.0.0.0 --port 8000`
- **Mirror**: `backend/pyproject.toml` for deps, `backend/.python-version` for Python 3.11
- **Validate**: `docker build -t ai-interviewer-backend ./backend`

### Task 3: Create worker Dockerfile

- **File**: `backend/Dockerfile.worker`
- **Action**: CREATE
- **Implement**:
  - Same base + dependency install as Task 2
  - Copy same source files
  - CMD: `uv run python -m agent.worker start`
  - No port exposed (outbound-only to LiveKit Cloud)
- **Mirror**: `backend/agent/worker.py:197-198`
- **Validate**: `docker build -f backend/Dockerfile.worker -t ai-interviewer-worker ./backend`

### Task 4: Create frontend nginx config

- **File**: `frontend/nginx.conf`
- **Action**: CREATE
- **Implement**:
  ```nginx
  server {
      listen 80;
      root /usr/share/nginx/html;
      index index.html;

      location /api/ {
          proxy_pass http://backend:8000/;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;
          client_max_body_size 10M;
      }

      location / {
          try_files $uri $uri/ /index.html;
      }
  }
  ```
  Nginx proxies `/api/*` to the backend container internally (stripping the `/api` prefix via trailing slash on `proxy_pass`). The backend is never exposed to the internet.
- **Mirror**: `samples/docker-compose.yml` — backend has no ports, frontend handles routing
- **Validate**: Included in frontend Docker build

### Task 5: Create frontend Dockerfile

- **File**: `frontend/Dockerfile`
- **Action**: CREATE
- **Implement**:
  - Stage 1 (`build`): `node:20-alpine`, workdir `/app`
    - Copy `package.json` + `package-lock.json`, run `npm ci`
    - Copy all source
    - `ARG VITE_API_URL` + `ARG VITE_LIVEKIT_URL` → set as ENV
    - Run `npm run build`
  - Stage 2: `nginx:alpine`
    - Copy `nginx.conf` → `/etc/nginx/conf.d/default.conf`
    - Copy `--from=build /app/dist` → `/usr/share/nginx/html`
    - Expose 80
- **Mirror**: `frontend/package.json` — `"build": "tsc -b && vite build"`
- **Validate**: `docker build --build-arg VITE_API_URL=https://aura.techa.pro/api --build-arg VITE_LIVEKIT_URL=wss://ai-interview-q1vqcy5r.livekit.cloud -t ai-interviewer-frontend ./frontend`

### Task 6: Create docker-compose.yml

- **File**: `docker-compose.yml`
- **Action**: CREATE
- **Implement**:
  ```yaml
  services:
    backend:
      build: ./backend
      container_name: aura-backend
      env_file: .env
      restart: unless-stopped
      # No ports exposed — only reachable by frontend/worker on internal network

    worker:
      build:
        context: ./backend
        dockerfile: Dockerfile.worker
      container_name: aura-worker
      env_file: .env
      environment:
        - BACKEND_URL=http://backend:8000
      depends_on:
        - backend
      restart: unless-stopped
      # No ports exposed — connects outbound to LiveKit Cloud only

    frontend:
      build:
        context: ./frontend
        args:
          VITE_API_URL: /api
          VITE_LIVEKIT_URL: ${LIVEKIT_URL}
      container_name: aura-frontend
      ports:
        - "127.0.0.1:3000:80"
      depends_on:
        - backend
      restart: unless-stopped
  ```
  All secrets and config come from `.env` (gitignored). `VITE_API_URL` is always `/api` (relative, proxied by nginx). `VITE_LIVEKIT_URL` is pulled from the same `.env` file via variable interpolation. `BACKEND_URL` is the only hardcoded value — it's the internal Docker network address, same for everyone.
- **Mirror**: `samples/docker-compose.yml` — backend hidden, frontend exposed
- **Validate**: `docker compose config`

### Task 7: Create .env.example template

- **File**: `.env.example`
- **Action**: CREATE
- **Implement**:
  ```env
  # OpenRouter (Pydantic AI agents: parser, evaluator, reporter)
  OPENROUTER_API_KEY=

  # LiveKit Cloud
  LIVEKIT_URL=wss://your-app.livekit.cloud
  LIVEKIT_API_KEY=
  LIVEKIT_API_SECRET=

  # OpenAI (LiveKit plugins: STT, LLM, TTS)
  OPENAI_API_KEY=

  # Your domain (used for CORS)
  DOMAIN=https://yourdomain.com
  ```
  Users copy this to `.env` and fill in their values. The `.env` file is gitignored.
- **Mirror**: `backend/.env.example`
- **Validate**: File exists

### Task 8: Create DEPLOY.md

- **File**: `DEPLOY.md`
- **Action**: CREATE
- **Implement**: Deployment guide covering:
  1. Prerequisites (Docker, Docker Compose, a reverse proxy like Caddy/nginx)
  2. Clone repo
  3. `cp .env.example .env` and fill in API keys + your domain
  4. `docker compose up -d --build`
  5. Point your reverse proxy at port 3000. Example Caddy config:
     ```
     yourdomain.com {
         reverse_proxy localhost:3000
     }
     ```
  6. Verify: `curl https://yourdomain.com/api/health`
  7. Update workflow: `git pull && docker compose up -d --build`
- **Mirror**: Generic template-friendly docs
- **Validate**: Manual review

---

## Validation

```bash
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:3000/api/health
curl http://localhost:3000/
curl https://aura.techa.pro/api/health
```

---

## Acceptance Criteria

- [ ] All 3 containers build successfully
- [ ] Backend responds at `https://aura.techa.pro/api/health`
- [ ] Frontend loads at `https://aura.techa.pro`
- [ ] Resume upload works (CORS configured correctly)
- [ ] LiveKit worker connects to LiveKit Cloud
- [ ] Voice interview session works end-to-end
- [ ] Client-side routing works (refresh on `/interview` doesn't 404)
