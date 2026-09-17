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


def get_oauth_session_secret() -> str:
    """Return the secret signing the OAuth session cookie, defaulting to JWT_SECRET.

    ``OAUTH_SESSION_SECRET`` lets operators decouple cookie signing from the JWT
    secret. When set it must pass the same strength rules as ``JWT_SECRET``;
    when unset (or weak outside production) the validated ``JWT_SECRET`` is
    used so exactly one session secret exists. A separate-but-valid secret
    must never silently coexist with a second ``SessionMiddleware`` — the
    middleware is registered exactly once in ``api/main.py`` with this value.
    """
    raw = os.getenv("OAUTH_SESSION_SECRET", "")
    if raw:
        if not _is_strong_secret(raw):
            if get_environment() == "production":
                raise RuntimeError(
                    "OAUTH_SESSION_SECRET is set but is weak (must be >= 32 chars "
                    "and not a known default). Either generate one with: "
                    "python -c 'import secrets; print(secrets.token_hex(32))' "
                    "or unset it to sign the session cookie with JWT_SECRET."
                )
            print(
                "WARNING: OAUTH_SESSION_SECRET is set but is weak; signing the "
                "session cookie with JWT_SECRET instead."
            )
            return JWT_SECRET
        return raw
    return JWT_SECRET


# Eagerly resolve at import time so a misconfiguration crashes the worker at
# boot rather than at the first authenticated request. Tests that need to
# exercise the failure path can import ``_is_strong_secret`` directly.
JWT_SECRET: str = get_jwt_secret()
ENVIRONMENT: str = get_environment()
OAUTH_SESSION_SECRET: str = get_oauth_session_secret()


def get_recruiter_monthly_limit() -> int:
    """Return the max interviews a recruiter can redeem per calendar month.

    Defaults to 20; falls back to 20 on a malformed value. This bounds voice
    spend per recruiter — each redeemed invite costs roughly $0.10-0.25.
    """
    raw = os.getenv("RECRUITER_MONTHLY_LIMIT", "20")
    try:
        value = int(raw)
    except ValueError:
        return 20
    return value if value > 0 else 20


RECRUITER_MONTHLY_LIMIT: int = get_recruiter_monthly_limit()


# --- AI model configuration -------------------------------------------------
#
# Every model the application talks to is selectable via env, so cost/quality
# tradeoffs can be changed without touching code. Pydantic AI agents use the
# provider-prefixed format (``openrouter:<model>``); LiveKit Inference models
# use ``<provider>/<model>`` (e.g. ``deepgram/nova-3``). The voice-pipeline LLM
# and STT (LIVEKIT_LLM_MODEL / LIVEKIT_STT_MODEL, resolved in agent/worker.py)
# accept both formats: an ``openrouter:`` prefix bills those calls to the
# OpenRouter account, an unprefixed ``<provider>/<model>`` bills them to
# LiveKit Inference.

_DEFAULT_REASONING_MODEL = "openrouter:google/gemini-2.0-flash-001"
_DEFAULT_VOICE_LLM_MODEL = "openai/gpt-4o-mini"


def get_reasoning_model(agent: str) -> str:
    """Resolve the model string for a Pydantic AI reasoning agent.

    The per-agent var (``PARSER_MODEL`` / ``EVALUATOR_MODEL`` /
    ``REPORTER_MODEL``) wins over the shared ``REASONING_MODEL``, which falls
    back to the built-in default. Empty or whitespace-only values count as
    unset so a commented-out line in .env degrades gracefully. The string is
    not validated here — an unsupported provider prefix fails loudly when the
    agent is constructed, i.e. at process boot.
    """
    per_agent = os.getenv(f"{agent.upper()}_MODEL", "").strip()
    if per_agent:
        return per_agent
    return os.getenv("REASONING_MODEL", "").strip() or _DEFAULT_REASONING_MODEL


def get_voice_llm_model() -> str:
    """Resolve the voice-pipeline LLM used by the LiveKit AgentSession.

    ``openrouter:<model>`` routes through OpenRouter (worker-side, billed to
    OPENROUTER_API_KEY); ``<provider>/<model>`` routes through LiveKit
    Inference (billed to the LiveKit account). The routing itself happens in
    ``agent/worker.create_voice_llm``.
    """
    return os.getenv("LIVEKIT_LLM_MODEL", "").strip() or _DEFAULT_VOICE_LLM_MODEL


# Eagerly resolved at import so a malformed model name crashes the process at
# boot (Agent construction) rather than mid-interview.
PARSER_MODEL: str = get_reasoning_model("parser")
EVALUATOR_MODEL: str = get_reasoning_model("evaluator")
REPORTER_MODEL: str = get_reasoning_model("reporter")
LIVEKIT_LLM_MODEL: str = get_voice_llm_model()
