# Plan: Redis-backed Rate Limiting

## Summary

Replace slowapi's in-memory rate limit storage with Redis so that rate limits persist across backend restarts and are shared across instances. Uses the existing `REDIS_URL` environment variable with an in-memory fallback for graceful degradation.

## User Story

As a platform operator
I want rate limits backed by Redis
So that limits persist across deploys and are enforced consistently across backend instances

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | backend (rate limiting) |
| Jira Issue | N/A |

---

## Patterns to Follow

### Environment Variables
```python
# SOURCE: backend/api/main.py:2,24-25
import os
api_key = os.getenv("LIVEKIT_API_KEY")
```

### Slowapi Limiter Init
```python
# SOURCE: backend/api/main.py:9-10
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
```

### .env.example Format
```bash
# SOURCE: .env.example:1-2
OPENROUTER_API_KEY=
LIVEKIT_URL=wss://your-app.livekit.cloud
```

### Tests (httpx AsyncClient + mock)
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
| `backend/pyproject.toml` | UPDATE | Add `redis` dependency |
| `backend/api/main.py` | UPDATE | Pass `storage_uri` and `in_memory_fallback_enabled` to Limiter |
| `.env.example` | UPDATE | Document `REDIS_URL` variable |

---

## Tasks

### Task 1: Add `redis` dependency

- **File**: `backend/pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `"redis>=5.0"` to the `dependencies` list
- **Mirror**: `backend/pyproject.toml:10-22` - follow existing dependency format
- **Validate**: `cd backend && uv sync`

### Task 2: Configure Limiter with Redis storage

- **File**: `backend/api/main.py`
- **Action**: UPDATE
- **Implement**: Read `REDIS_URL` from env and pass to Limiter:
  ```python
  limiter = Limiter(
      key_func=get_remote_address,
      storage_uri=os.getenv("REDIS_URL"),
      in_memory_fallback_enabled=True,
  )
  ```
  When `REDIS_URL` is `None`, slowapi falls back to in-memory automatically. The `in_memory_fallback_enabled=True` also handles Redis going down at runtime.
- **Mirror**: `backend/api/main.py:9-10` - existing Limiter init
- **Validate**: `cd backend && uv run python -c "from api.main import app; print('OK')"`

### Task 3: Document `REDIS_URL` in .env.example

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Add a `REDIS_URL` entry with a comment:
  ```bash
  # Redis (rate limiting)
  REDIS_URL=redis://localhost:6379/0
  ```
- **Mirror**: `.env.example:1-12` - follow existing format
- **Validate**: Visual inspection

---

## Validation

```bash
# Dependency resolution
cd backend && uv sync

# Import check
uv run python -c "from api.main import app; print('OK')"

# Tests (REDIS_URL unset → in-memory fallback)
uv run pytest
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Redis unavailable at startup | `in_memory_fallback_enabled=True` degrades gracefully to in-memory |
| Redis goes down at runtime | Same fallback handles transient failures |
| Tests hit rate-limited endpoints | `REDIS_URL` not set in test env → in-memory store resets per process, existing tests unaffected |
| `redis` package version conflict | Pinned to `>=5.0` which is compatible with `limits` library used by slowapi |

---

## Acceptance Criteria

- [ ] `redis` package in `pyproject.toml` dependencies
- [ ] `Limiter` uses `storage_uri=os.getenv("REDIS_URL")` with `in_memory_fallback_enabled=True`
- [ ] `.env.example` documents `REDIS_URL`
- [ ] `uv sync` succeeds
- [ ] All existing tests pass
- [ ] Rate limits persist across backend restarts when `REDIS_URL` is set
