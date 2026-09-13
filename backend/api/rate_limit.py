"""Shared slowapi rate limiter.

Lives in its own module so both ``api.main`` and ``api.auth`` can decorate
endpoints without a circular import (main imports the auth router).
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=lambda request: request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or get_remote_address(request),
    storage_uri=os.getenv("REDIS_URL"),
    in_memory_fallback_enabled=True,
)
