import os
from fastapi import Request, HTTPException
import jwt
from db.crud import get_user_by_id
from db.database import async_session
from db.models import User

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
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

    if WORKER_API_KEY and token == WORKER_API_KEY:
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
