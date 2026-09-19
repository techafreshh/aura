import os
import json
import re
import secrets
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from db.crud import (
    upsert_oauth_user,
    get_user_by_email,
    store_verification_token,
    mark_email_verified,
    store_reset_token,
    set_user_password,
    set_user_role,
)
from db.database import async_session
from db.models import User
from api.deps import get_current_user, _WorkerUser
from api.rate_limit import limiter
from utils.config import JWT_SECRET, ENVIRONMENT
from utils.email import (
    send_email,
    verification_email_html,
    welcome_email_html,
    password_reset_email_html,
    get_public_api_url,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Where email links point: the browser-reachable base of this API. In the
# docker deployment the frontend's nginx proxies /api/<path> to this app.
PUBLIC_API_URL = get_public_api_url(FRONTEND_URL, ENVIRONMENT)

VERIFICATION_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(hours=1)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# bcrypt silently truncates input beyond 72 bytes, so reject those upfront.
_MAX_PASSWORD_BYTES = 72


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=64)
    name: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=64)


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=255)
    new_password: str = Field(min_length=8, max_length=64)


oauth = OAuth()

oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="github",
    client_id=os.getenv("GITHUB_CLIENT_ID", ""),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "user:email"},
)


def _make_jwt(user_id: str, email: str, role: str, name: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        # ``role`` is informational only — the backend always re-reads
        # ``role`` from the DB on each request (see api/deps.get_current_user)
        # so an admin demoted via env var cannot keep privileges until the
        # token expires.
        "role": role,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise HTTPException(400, "Password is too long.")


def _clean_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    name = re.sub(r"<[^>]+>", "", name)
    name = re.sub(r"\s+", " ", name).strip()[:100]
    return name


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _check_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


async def _send_verification(to: str, name: str, verify_url: str) -> None:
    await send_email(to, "Verify your email — Aura", verification_email_html(name, verify_url))


async def _send_welcome(to: str, name: str) -> None:
    await send_email(to, "Welcome to Aura", welcome_email_html(name, FRONTEND_URL))


async def _send_password_reset(to: str, name: str, reset_url: str) -> None:
    await send_email(to, "Reset your password — Aura", password_reset_email_html(name, reset_url))


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_recruiter": bool(getattr(user, "is_recruiter", False)),
        "avatar_url": user.avatar_url,
    }


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return _user_payload(user)


@router.post("/logout")
async def logout():
    return {"status": "ok"}


def _duplicate_account_error(user: User | None) -> HTTPException:
    """409 for an already-registered email, hinting at provider-only accounts."""
    if user is not None and not user.password_hash:
        return HTTPException(
            409,
            "This email is registered with Google/GitHub. Sign in with that provider instead.",
        )
    return HTTPException(409, "An account with this email already exists.")


@router.post("/register")
@limiter.limit("5/hour")
async def register(request: Request, payload: RegisterRequest, background_tasks: BackgroundTasks):
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "Please enter a valid email address.")
    _validate_password(payload.password)
    name = _clean_name(payload.name)

    async with async_session() as db:
        user = await get_user_by_email(db, email)

        if user and user.email_verified:
            raise _duplicate_account_error(user)

        if user is not None and user.provider != "email":
            # OAuth-linked accounts — including legacy rows the migration left
            # email_verified=False — are claimed through their provider, never by
            # an unauthenticated email/password registration. Letting register
            # set a password here would let an attacker pre-load one that OAuth
            # verification later activates (account takeover).
            raise _duplicate_account_error(user)

        password_hash = await run_in_threadpool(_hash_password, payload.password)

        if user is None:
            user = User(
                email=email,
                name=name or email.split("@")[0],
                provider="email",
                provider_id=email,
                password_hash=password_hash,
                email_verified=False,
            )
            if email == ADMIN_EMAIL:
                user.role = "admin"
            db.add(user)
            try:
                await db.commit()
                await db.refresh(user)
            except IntegrityError:
                # A concurrent registration for the same email won the insert.
                # Resolve the winner and treat it as an existing account.
                await db.rollback()
                user = await get_user_by_email(db, email)
                if user is None or user.email_verified:
                    raise _duplicate_account_error(user)
                user.password_hash = password_hash
                await db.commit()
                await db.refresh(user)
        else:
            # Existing account that is not verified: a legacy OAuth row the
            # migration left email_verified=False, or an abandoned email signup.
            # Store the submitted password so completing verification actually
            # enables password login instead of leaving password_hash unset.
            user.password_hash = password_hash
            await db.commit()
            await db.refresh(user)

        raw_token = _new_token()
        await store_verification_token(
            db, user, _hash_token(raw_token), datetime.now(timezone.utc) + VERIFICATION_TOKEN_TTL
        )

    verify_url = f"{PUBLIC_API_URL}/auth/verify-email?token={raw_token}"
    background_tasks.add_task(_send_verification, user.email, user.name, verify_url)
    return {"message": "Check your inbox — we sent you a verification link."}


@router.post("/login")
@limiter.limit("10/hour")
async def login(request: Request, payload: LoginRequest):
    email = _normalize_email(payload.email)

    async with async_session() as db:
        user = await get_user_by_email(db, email)
        if not user or not await run_in_threadpool(_check_password, payload.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password.")
        if not user.email_verified:
            raise HTTPException(
                403,
                {"code": "email_not_verified", "message": "Please verify your email address before signing in."},
            )
        if user.email.lower() == ADMIN_EMAIL and user.role != "admin":
            user.role = "admin"
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()

    return {"token": _make_jwt(user.id, user.email, user.role, user.name), "user": _user_payload(user)}


# Declared before the /{provider} catch-all below so "verify-email" is not
# parsed as an OAuth provider name.
@router.get("/verify-email")
@limiter.limit("30/hour")
async def verify_email(request: Request, token: str = Query("")):
    status = "invalid"
    if token:
        async with async_session() as db:
            found = await db.execute(
                select(User).where(User.verification_token_hash == _hash_token(token))
            )
            user = found.scalar_one_or_none()
            if user:
                expires_at = user.verification_token_expires_at
                if expires_at is None or _as_utc(expires_at) < datetime.now(timezone.utc):
                    status = "expired"
                else:
                    await mark_email_verified(db, user)
                    status = "success"
    return RedirectResponse(f"{FRONTEND_URL}/auth/verified?status={status}", status_code=302)


@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(request: Request, payload: EmailRequest, background_tasks: BackgroundTasks):
    email = _normalize_email(payload.email)

    async with async_session() as db:
        user = await get_user_by_email(db, email)
        if user and not user.email_verified:
            raw_token = _new_token()
            await store_verification_token(
                db, user, _hash_token(raw_token), datetime.now(timezone.utc) + VERIFICATION_TOKEN_TTL
            )
            verify_url = f"{PUBLIC_API_URL}/auth/verify-email?token={raw_token}"
            background_tasks.add_task(_send_verification, user.email, user.name, verify_url)

    return {"message": "If that account still needs verification, a new link is on its way."}


@router.post("/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(request: Request, payload: EmailRequest, background_tasks: BackgroundTasks):
    email = _normalize_email(payload.email)

    async with async_session() as db:
        user = await get_user_by_email(db, email)
        # OAuth-only accounts have no password to reset; stay silent to avoid
        # leaking which emails have password accounts.
        if user and user.password_hash:
            raw_token = _new_token()
            await store_reset_token(
                db, user, _hash_token(raw_token), datetime.now(timezone.utc) + RESET_TOKEN_TTL
            )
            reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
            background_tasks.add_task(_send_password_reset, user.email, user.name, reset_url)

    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password")
@limiter.limit("5/hour")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    _validate_password(payload.new_password)

    async with async_session() as db:
        found = await db.execute(
            select(User).where(User.reset_token_hash == _hash_token(payload.token))
        )
        user = found.scalar_one_or_none()
        expires_at = user.reset_token_expires_at if user else None
        if not user or expires_at is None or _as_utc(expires_at) < datetime.now(timezone.utc):
            raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
        new_password_hash = await run_in_threadpool(_hash_password, payload.new_password)
        await set_user_password(db, user, new_password_hash)

    return {"message": "Password updated. You can now sign in."}


class RoleChoice(BaseModel):
    role: Literal["candidate", "recruiter"]


@router.post("/role")
@limiter.limit("20/hour")
async def set_role(request: Request, choice: RoleChoice, user=Depends(get_current_user)):
    """Role picker: choose the starting mode (candidate or recruiter).

    Choosing ``recruiter`` permanently grants the ``is_recruiter`` capability
    (dual roles — picking ``candidate`` later never revokes it; active mode is
    a frontend-only concern). Admins keep their role and cannot demote
    themselves via this endpoint. Returns a fresh JWT plus the updated user
    since the token carries a (read-only) role claim the frontend relies on.
    """
    if isinstance(user, _WorkerUser):
        raise HTTPException(403, "Workers cannot set a role")
    if user.role not in ("", "candidate", "recruiter"):
        raise HTTPException(403, "Admins cannot change role")

    async with async_session() as db:
        updated = await set_user_role(db, user.id, choice.role)
    if not updated:
        raise HTTPException(404, "User not found")

    return {
        "token": _make_jwt(updated.id, updated.email, updated.role, updated.name),
        "user": _user_payload(updated),
    }


@router.get("/{provider}")
async def oauth_login(request: Request, provider: str):
    if provider not in ("google", "github"):
        raise HTTPException(400, "Unsupported provider")
    client = oauth.create_client(provider)
    redirect_uri = request.url_for("oauth_callback", provider=provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback", name="oauth_callback")
async def oauth_callback(request: Request, provider: str, background_tasks: BackgroundTasks):
    if provider not in ("google", "github"):
        raise HTTPException(400, "Unsupported provider")

    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)

    if provider == "google":
        user_info = token.get("userinfo") or await client.parse_id_token(request, token)
        email = user_info["email"]
        name = user_info.get("name", "")
        avatar_url = user_info.get("picture")
        provider_id = user_info["sub"]
        if user_info.get("email_verified") is not True:
            raise HTTPException(400, "OAuth email is not verified")
    else:
        resp = await client.get("user", token=token)
        profile = resp.json()
        emails_resp = await client.get("user/emails", token=token)
        emails = emails_resp.json()
        email = next((e["email"] for e in emails if e.get("primary") and e.get("verified")), "")
        if not email:
            email = next((e["email"] for e in emails if e.get("verified")), "")
        if not email:
            raise HTTPException(400, "Could not retrieve a verified email from GitHub")
        name = profile.get("name") or profile.get("login", "")
        avatar_url = profile.get("avatar_url")
        provider_id = str(profile["id"])

    if not email:
        raise HTTPException(400, "Could not retrieve email from provider")
    email = email.strip().lower()

    async with async_session() as db:
        user, created = await upsert_oauth_user(
            db,
            email=email,
            name=name,
            provider=provider,
            provider_id=provider_id,
            avatar_url=avatar_url,
        )
        if ADMIN_EMAIL and user.email.lower() == ADMIN_EMAIL:
            user.role = "admin"
            await db.commit()

    # Provider-verified emails need no verification; greet new users once.
    if created:
        background_tasks.add_task(_send_welcome, user.email, user.name)

    jwt_token = _make_jwt(user.id, user.email, user.role, user.name)

    user_data = urllib.parse.quote(json.dumps(_user_payload(user)))
    # Use URL fragment (#) so the token is NOT sent to servers in Referer headers
    # or logged in access logs. The frontend must clear the fragment after reading.
    return RedirectResponse(f"{FRONTEND_URL}/auth/callback#token={jwt_token}&user={user_data}")
