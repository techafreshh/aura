import os
import json
import urllib.parse
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from db.crud import upsert_user
from db.database import async_session
from api.deps import get_current_user

import jwt

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

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
    from datetime import datetime, timezone, timedelta
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "avatar_url": user.avatar_url,
    }


@router.post("/logout")
async def logout():
    return {"status": "ok"}


@router.get("/{provider}")
async def oauth_login(request: Request, provider: str):
    if provider not in ("google", "github"):
        raise HTTPException(400, "Unsupported provider")
    client = oauth.create_client(provider)
    redirect_uri = request.url_for("oauth_callback", provider=provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback", name="oauth_callback")
async def oauth_callback(request: Request, provider: str):
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
    else:
        resp = await client.get("user", token=token)
        profile = resp.json()
        email = profile.get("email") or ""
        if not email:
            emails_resp = await client.get("user/emails", token=token)
            emails = emails_resp.json()
            email = next((e["email"] for e in emails if e.get("primary")), emails[0]["email"] if emails else "")
        name = profile.get("name") or profile.get("login", "")
        avatar_url = profile.get("avatar_url")
        provider_id = str(profile["id"])

    if not email:
        raise HTTPException(400, "Could not retrieve email from provider")

    async with async_session() as db:
        user = await upsert_user(
            db,
            email=email,
            name=name,
            provider=provider,
            provider_id=provider_id,
            avatar_url=avatar_url,
        )
        if user.email == ADMIN_EMAIL:
            user.role = "admin"
            await db.commit()

    jwt_token = _make_jwt(user.id, user.email, user.role, user.name)

    user_data = urllib.parse.quote(json.dumps({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "avatar_url": user.avatar_url,
    }))
    return RedirectResponse(f"{FRONTEND_URL}/auth/callback?token={jwt_token}&user={user_data}")
