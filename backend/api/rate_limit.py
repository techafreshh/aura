"""Shared slowapi rate limiter.

Lives in its own module so both ``api.main`` and ``api.auth`` can decorate
endpoints without a circular import (main imports the auth router).
"""

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Rate-limit key: the peer address as seen by our nearest trusted proxy.

    nginx appends the actual peer address to ``X-Forwarded-For``
    (``$proxy_add_x_forwarded_for``), so the *last* hop is the value our proxy
    vouched for. Using the first hop would let a client send a different
    spoofed value per request and bypass every per-IP limit.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if hops:
        return hops[-1]
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_ip,
    storage_uri=os.getenv("REDIS_URL"),
    in_memory_fallback_enabled=True,
)
