import os
import hmac
from fastapi import Request, HTTPException
import jwt
from db.crud import get_user_by_id
from db.database import async_session
from db.models import User
from utils.config import JWT_SECRET

WORKER_API_KEY = os.getenv("WORKER_API_KEY", "")


class _WorkerUser:
    """Sentinel object returned when the caller authenticates with WORKER_API_KEY."""
    id = "worker"
    role = "worker"


async def get_current_user(request: Request) -> User | _WorkerUser:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(401, "Not authenticated")

    token = auth_header.removeprefix("Bearer ").strip()

    # Constant-time comparison avoids leaking key length/content via timing.
    if WORKER_API_KEY and hmac.compare_digest(token, WORKER_API_KEY):
        return _WorkerUser()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

    async with async_session() as db:
        user = await get_user_by_id(db, payload["sub"])

    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_admin(user) -> None:
    if getattr(user, "role", None) != "admin":
        raise HTTPException(403, "Admin access required")


def require_recruiter(user) -> None:
    """Recruiter capability gate.

    Dual roles: a user qualifies via the one-way ``is_recruiter`` grant, the
    legacy ``role == "recruiter"`` string (rows created before the flag
    existed, and test stubs), or being an admin. Lives next to
    ``require_admin`` so both the invites endpoints and the profiles router
    can share it without a circular import through ``api.main``.
    """
    role = getattr(user, "role", None)
    if role == "admin" or role == "recruiter" or getattr(user, "is_recruiter", False):
        return
    raise HTTPException(403, "Recruiter access required")
