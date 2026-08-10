from datetime import datetime, timezone
from sqlalchemy import select, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, OAuthIdentity, InterviewSession


async def upsert_user(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    provider: str,
    provider_id: str,
    avatar_url: str | None = None,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        user.name = name
        user.avatar_url = avatar_url
        user.last_login_at = datetime.now(timezone.utc)
    else:
        user = User(
            email=email,
            name=name,
            provider=provider,
            provider_id=provider_id,
            avatar_url=avatar_url,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user


async def upsert_oauth_user(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    provider: str,
    provider_id: str,
    avatar_url: str | None = None,
) -> User:
    """Resolve a provider identity, linking verified providers by email."""
    email = email.strip().lower()
    identity_result = await db.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_id == provider_id,
        )
    )
    identity = identity_result.scalar_one_or_none()
    if identity:
        user = await get_user_by_id(db, identity.user_id)
        if user:
            user.name, user.avatar_url = name, avatar_url
            user.last_login_at = datetime.now(timezone.utc)
            identity.email = email
            await db.commit()
            await db.refresh(user)
            return user

    user_result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(email=email, name=name, provider=provider, provider_id=provider_id, avatar_url=avatar_url)
        db.add(user)
        await db.flush()
    else:
        user.name, user.avatar_url = name, avatar_url
        user.last_login_at = datetime.now(timezone.utc)

    db.add(OAuthIdentity(user_id=user.id, provider=provider, provider_id=provider_id, email=email))
    try:
        await db.commit()
    except IntegrityError:
        # OAuth callbacks can be retried or completed in concurrent tabs.
        await db.rollback()
        existing_identity = await db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider,
                OAuthIdentity.provider_id == provider_id,
            )
        )
        identity = existing_identity.scalar_one_or_none()
        if identity:
            existing_user = await get_user_by_id(db, identity.user_id)
            if existing_user:
                return existing_user
        user_result = await db.execute(select(User).where(func.lower(User.email) == email))
        user = user_result.scalar_one_or_none()
        if not user:
            raise
        db.add(OAuthIdentity(user_id=user.id, provider=provider, provider_id=provider_id, email=email))
        await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_session(
    db: AsyncSession,
    *,
    user_id: str,
    candidate_name: str,
    plan_json: str,
    session_id: str | None = None,
) -> InterviewSession:
    session = InterviewSession(
        user_id=user_id,
        candidate_name=candidate_name,
        plan_json=plan_json,
        status="pending",
        **({"id": session_id} if session_id else {}),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: str) -> InterviewSession | None:
    result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
    return result.scalar_one_or_none()


async def update_session_report(
    db: AsyncSession,
    session_id: str,
    report_json: str,
    status: str = "completed",
) -> None:
    session = await get_session(db, session_id)
    if session:
        session.report_json = report_json
        session.status = status
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def update_session_transcript(
    db: AsyncSession,
    session_id: str,
    transcript_json: str,
) -> None:
    session = await get_session(db, session_id)
    if session:
        session.transcript_json = transcript_json
        await db.commit()


async def list_user_sessions(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[InterviewSession]:
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == user_id)
        .order_by(desc(InterviewSession.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def list_all_sessions(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[InterviewSession]:
    stmt = select(InterviewSession).order_by(desc(InterviewSession.created_at))
    if status:
        stmt = stmt.where(InterviewSession.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())
