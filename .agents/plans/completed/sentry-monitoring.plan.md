# Plan: Sentry Cloud Monitoring

## Summary

Add full-stack error tracking and performance monitoring using Sentry Cloud (free tier). The FastAPI backend, LiveKit worker, and React frontend will all report errors and traces to Sentry, with email alerts configured for new issues and error spikes.

## User Story

As a developer
I want real-time error tracking, performance monitoring, and email alerts across all services
So that I'm notified immediately when something breaks in production

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | backend, worker, frontend, docker |
| Jira Issue | N/A |

---

## Patterns to Follow

### Environment Variables
```python
# SOURCE: backend/api/main.py:2
import os

# SOURCE: backend/api/main.py:18
storage_uri=os.getenv("REDIS_URL"),
```

### SDK Initialization (before app)
```python
# SOURCE: backend/api/main.py:16-22
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL"),
    in_memory_fallback_enabled=True,
)
app = FastAPI(title="AI Interviewer API")
```

### Worker Initialization
```python
# SOURCE: backend/agent/worker.py:28-31
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("voice-agent")
```

### Frontend Entry Point
```tsx
# SOURCE: frontend/src/main.tsx:1-9
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
```

### Docker Build Args
```dockerfile
# SOURCE: frontend/Dockerfile:10-12
ARG VITE_API_URL
ARG VITE_LIVEKIT_URL
ENV VITE_API_URL=$VITE_API_URL
```

### Docker Compose Build Args
```yaml
# SOURCE: docker-compose.yml:16-19
frontend:
  build:
    context: ./frontend
    args:
      VITE_API_URL: /api
      VITE_LIVEKIT_URL: ${LIVEKIT_URL}
```

### Tests
```python
# SOURCE: backend/tests/test_api.py:1-6
import pytest
import os
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from api.main import app, plans
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `sentry-sdk[fastapi]` dependency |
| `backend/api/main.py` | UPDATE | Initialize Sentry before FastAPI app |
| `backend/agent/worker.py` | UPDATE | Initialize Sentry after `load_dotenv()` |
| `frontend/package.json` | UPDATE | Add `@sentry/react` and `@sentry/vite-plugin` |
| `frontend/src/main.tsx` | UPDATE | Add `Sentry.init()` and wrap app with ErrorBoundary |
| `frontend/vite.config.ts` | UPDATE | Add Sentry Vite plugin for source maps |
| `frontend/Dockerfile` | UPDATE | Add `SENTRY_AUTH_TOKEN` build arg |
| `docker-compose.yml` | UPDATE | Pass `VITE_SENTRY_DSN` and `SENTRY_AUTH_TOKEN` to frontend build |
| `.env.example` | UPDATE | Add `SENTRY_DSN`, `VITE_SENTRY_DSN`, `SENTRY_AUTH_TOKEN` |
| `backend/.env.example` | UPDATE | Add `SENTRY_DSN` |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add Sentry Python SDK dependency

- **File**: `backend/pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `"sentry-sdk[fastapi]>=2.0"` to the `dependencies` list
- **Mirror**: `backend/pyproject.toml:10-22` — follow existing dependency format with minimum version pins
- **Validate**: `cd backend && uv sync`

### Task 2: Initialize Sentry in FastAPI backend

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Add at the top of the file (after imports, before `limiter` creation):
  ```python
  import sentry_sdk

  sentry_sdk.init(
      dsn=os.getenv("SENTRY_DSN"),
      traces_sample_rate=1.0,
      environment=os.getenv("ENVIRONMENT", "production"),
  )
  ```
  The SDK auto-detects FastAPI and instruments all routes. No middleware needed.
- **Mirror**: `backend/api/main.py:16-22` — initialization before app creation, env-driven config
- **Validate**: `cd backend && uv run python -c "from api.main import app; print('OK')"`

### Task 3: Initialize Sentry in the LiveKit worker

- **File**: `backend/agent/worker.py`
- **Action**: UPDATE
- **Implement**: Add after `load_dotenv()` (line 28), before the logger setup:
  ```python
  import sentry_sdk

  sentry_sdk.init(
      dsn=os.getenv("SENTRY_DSN"),
      traces_sample_rate=1.0,
      environment=os.getenv("ENVIRONMENT", "production"),
  )
  ```
- **Mirror**: `backend/agent/worker.py:28-31` — initialization after env loading, before logger
- **Validate**: `cd backend && uv run python -c "from agent.worker import entrypoint; print('OK')"`

### Task 4: Add Sentry React SDK dependencies

- **File**: `frontend/package.json`
- **Action**: UPDATE
- **Implement**: Add to `dependencies`:
  ```
  "@sentry/react": "^9.0.0"
  ```
  Add to `devDependencies`:
  ```
  "@sentry/vite-plugin": "^3.0.0"
  ```
- **Mirror**: `frontend/package.json` — follow existing version format with `^` prefix
- **Validate**: `cd frontend && npm install`

### Task 5: Initialize Sentry in React frontend

- **File**: `frontend/src/main.tsx`
- **Action**: UPDATE
- **Implement**: Add Sentry initialization before `createRoot()`:
  ```tsx
  import * as Sentry from '@sentry/react'

  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 1.0,
  })
  ```
  Wrap the app render with `Sentry.ErrorBoundary`:
  ```tsx
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <Sentry.ErrorBoundary fallback={<p>Something went wrong.</p>}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </Sentry.ErrorBoundary>
    </StrictMode>,
  )
  ```
- **Mirror**: `frontend/src/main.tsx:1-9` — imports at top, wrapping existing tree
- **Validate**: `cd frontend && npm run build`

### Task 6: Add Sentry Vite plugin for source maps

- **File**: `frontend/vite.config.ts`
- **Action**: UPDATE
- **Implement**: Add the Sentry Vite plugin to upload source maps at build time:
  ```ts
  import { sentryVitePlugin } from "@sentry/vite-plugin"

  export default defineConfig({
    build: {
      sourcemap: true,
    },
    plugins: [
      react(),
      sentryVitePlugin({
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        authToken: process.env.SENTRY_AUTH_TOKEN,
      }),
    ],
    // ... rest unchanged
  })
  ```
  The plugin silently skips upload if `SENTRY_AUTH_TOKEN` is not set (no build failure).
- **Mirror**: `frontend/vite.config.ts:1-12` — plugin added to existing plugins array
- **Validate**: `cd frontend && npm run build`

### Task 7: Update frontend Dockerfile for Sentry build args

- **File**: `frontend/Dockerfile`
- **Action**: UPDATE
- **Implement**: Add after existing `ARG`/`ENV` lines:
  ```dockerfile
  ARG VITE_SENTRY_DSN
  ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN

  ARG SENTRY_AUTH_TOKEN
  ENV SENTRY_AUTH_TOKEN=$SENTRY_AUTH_TOKEN
  ARG SENTRY_ORG
  ENV SENTRY_ORG=$SENTRY_ORG
  ARG SENTRY_PROJECT
  ENV SENTRY_PROJECT=$SENTRY_PROJECT
  ```
- **Mirror**: `frontend/Dockerfile:10-12` — existing ARG/ENV pattern
- **Validate**: `docker compose build frontend`

### Task 8: Update docker-compose.yml

- **File**: `docker-compose.yml`
- **Action**: UPDATE
- **Implement**: Add build args to the frontend service:
  ```yaml
  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_URL: /api
        VITE_LIVEKIT_URL: ${LIVEKIT_URL}
        VITE_SENTRY_DSN: ${VITE_SENTRY_DSN}
        SENTRY_AUTH_TOKEN: ${SENTRY_AUTH_TOKEN}
        SENTRY_ORG: ${SENTRY_ORG}
        SENTRY_PROJECT: ${SENTRY_PROJECT}
  ```
- **Mirror**: `docker-compose.yml:16-19` — existing build args pattern
- **Validate**: `docker compose config`

### Task 9: Update environment variable examples

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Add at the bottom:
  ```
  # Sentry (error monitoring)
  SENTRY_DSN=
  VITE_SENTRY_DSN=
  SENTRY_AUTH_TOKEN=
  SENTRY_ORG=
  SENTRY_PROJECT=
  ```
- **File**: `backend/.env.example`
- **Action**: UPDATE
- **Implement**: Add at the bottom:
  ```
  # Sentry (error monitoring)
  SENTRY_DSN=
  ```
- **Mirror**: `.env.example` and `backend/.env.example` — comment header + KEY=value format
- **Validate**: Visual inspection

### Task 10: Configure email alerts in Sentry (manual)

- **Action**: MANUAL (Sentry web UI)
- **Implement**:
  1. Go to sentry.io → Project Settings → Alerts
  2. Create issue alert: "When a new issue is created → Send email notification"
  3. Create metric alert: "When error count > 10 in 5 minutes → Send email"
  4. Verify email address in Settings → Notifications
- **Validate**: Trigger a test error, confirm email arrives

---

## Validation

```bash
# Backend type check and import
cd backend && uv run python -c "from api.main import app; print('OK')"

# Worker import
cd backend && uv run python -c "from agent.worker import entrypoint; print('OK')"

# Frontend build
cd frontend && npm run build

# Full Docker build
docker compose build

# Tests still pass
cd backend && uv run pytest
```

---

## Acceptance Criteria

- [ ] `sentry-sdk[fastapi]` added to backend dependencies
- [ ] Backend initializes Sentry before app creation
- [ ] Worker initializes Sentry after env loading
- [ ] Frontend initializes Sentry before render
- [ ] Frontend errors caught by ErrorBoundary
- [ ] Source maps uploaded during Docker build (when token provided)
- [ ] All env vars documented in `.env.example`
- [ ] Docker Compose builds successfully
- [ ] Existing tests still pass
- [ ] First error event visible in Sentry dashboard
- [ ] Email alert received on test error
