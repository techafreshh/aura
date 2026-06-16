from datetime import datetime, timezone
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, InterviewSession


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


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_session(
    db: AsyncSession,
    *,
    user_id: str,
    candidate_name: str,
    plan_json: str,
) -> InterviewSession:
    session = InterviewSession(
        user_id=user_id,
        candidate_name=candidate_name,
        plan_json=plan_json,
        status="pending",
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
