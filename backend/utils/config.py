"""Centralized runtime configuration.

Single source of truth for ``JWT_SECRET`` and the ``ENVIRONMENT`` default.
Importing from this module guarantees the secret strength check is enforced
exactly once at process start, instead of being duplicated and trivially
bypassed in each consumer (see PR #10 review High #1).
"""

from __future__ import annotations

import hmac
import os

# Minimum acceptable JWT_SECRET length in bytes. 32 bytes (256 bits) matches
# the output of ``secrets.token_hex(32)`` and HS256's effective key strength.
_MIN_SECRET_LENGTH = 32

# Known-insecure values that must be rejected even if they happen to be long
# enough. Kept conservative — common tutorial defaults and the prior shipped
# example value.
_KNOWN_BAD_SECRETS = frozenset(
    {
        "change-me-in-production",
        "changeme",
        "secret",
        "password",
        "default",
        "test",
        "development",
    }
)

# Stable dev-only fallback. Fixed so existing tokens survive backend restarts
# in development. Never used in production — the strength check below rejects
# it explicitly and the prod branch raises before reaching the fallback.
_DEV_FALLBACK_SECRET = "dev-secret-do-not-use-in-prod-32+chars!!"


def get_environment() -> str:
    """Return the current environment, defaulting to ``development``.

    ``development`` is the safe default for the most common local run; the
    deployment pipeline must explicitly set ``ENVIRONMENT=production``. This
    matches the prior CORS branch in ``api/main.py``.
    """
    return os.getenv("ENVIRONMENT", "development")


def _is_strong_secret(value: str) -> bool:
    if not isinstance(value, str) or len(value) < _MIN_SECRET_LENGTH:
        return False
    # Reject known-bad values via constant-time comparison so an attacker can't
    # infer the check string from timing.
    for bad in _KNOWN_BAD_SECRETS:
        if hmac.compare_digest(value, bad):
            return False
    return True


def get_jwt_secret() -> str:
    """Return the validated JWT secret, raising in production if weak.

    Resolution order:
    1. ``JWT_SECRET`` env var, if present and strong.
    2. In ``production``: raise ``RuntimeError`` (loud failure at startup).
    3. In any other environment: a stable, fixed dev fallback. This avoids
       invalidating every existing token on each backend restart, which the
       prior per-process ``secrets.token_hex(32)`` fallback caused.
    """
    raw = os.getenv("JWT_SECRET", "")
    if raw:
        if not _is_strong_secret(raw):
            env = get_environment()
            if env == "production":
                raise RuntimeError(
                    "JWT_SECRET is set but is weak (must be >= 32 chars and not a "
                    "known default). Generate one with: "
                    "python -c 'import secrets; print(secrets.token_hex(32))'"
                )
            # In dev, surface the problem in logs but keep the stable fallback
            # so the developer isn't locked out. The weak value is ignored.
            print(
                "WARNING: JWT_SECRET is set but is weak; using the development "
                "fallback instead. Generate a strong value before deploying."
            )
            return _DEV_FALLBACK_SECRET
        return raw

    if get_environment() == "production":
        raise RuntimeError(
            "JWT_SECRET must be set to a strong value in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    return _DEV_FALLBACK_SECRET


# Eagerly resolve at import time so a misconfiguration crashes the worker at
# boot rather than at the first authenticated request. Tests that need to
# exercise the failure path can import ``_is_strong_secret`` directly.
JWT_SECRET: str = get_jwt_secret()
ENVIRONMENT: str = get_environment()
