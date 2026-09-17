"""One-shot SQLite -> Postgres data migration.

Brings the DATABASE_URL target to Alembic head, then copies every row from
the SQLite source file in foreign-key order
(users -> oauth_identities -> interview_sessions -> interview_invites).
PKs are string UUIDs, so there are no sequences to reattach.

Datetimes need care: SQLite stores aware datetimes as UTC wall-time strings
and SQLAlchemy returns them naive, while the Postgres columns are
timestamptz — every datetime is coerced to UTC-aware before insert.

Usage (both databases must be reachable from where this runs — the backend
container on the compose network is the usual place):

    cd backend
    DATABASE_URL=postgresql+asyncpg://aura_user:pw@postgres:5432/aura \
        uv run python scripts/migrate_sqlite_to_postgres.py \
        [--source /app/data/aura.db]

Idempotent: rows are inserted with ON CONFLICT DO NOTHING, so a re-run after
a partial copy fills only the gaps. Source and target row counts are printed
per table and must match, or the script exits non-zero. The source file is
only ever read — rollback is simply unsetting DATABASE_URL and restarting.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script from anywhere; mirrors agent/worker.py.
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

from db.database import DATABASE_URL, DB_PATH

# FK-dependency order. sorted_tables would give the same order; keeping the
# list explicit makes the expected shape of the copy obvious in the report.
COPY_ORDER = ["users", "oauth_identities", "interview_sessions", "interview_invites"]

# asyncpg caps one statement at 65535 bind params; these tables have ~15
# columns, so 200 rows per statement stays far below the ceiling.
CHUNK_SIZE = 200


def _coerce(column: sa.Column, value):
    """Make a value read from SQLite safe for the matching Postgres column."""
    if value is None:
        return None
    if isinstance(column.type, sa.DateTime):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime) and value.tzinfo is None:
            # SQLite dropped the offset at write time; the app only ever
            # writes UTC, so the wall time IS UTC.
            value = value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(column.type, sa.Boolean):
        return bool(value)
    return value


async def _copy(source_path: Path) -> int:
    src_engine = create_async_engine(f"sqlite+aiosqlite:///{source_path}")
    dst_engine = create_async_engine(DATABASE_URL)

    copied: dict[str, int] = {}
    skipped: dict[str, str] = {}

    # One long-lived source connection for reflection, row reads, and
    # verification — an async connection can't outlive its ``async with``.
    async with src_engine.connect() as src_conn:
        def _reflect(sync_conn) -> sa.MetaData:
            meta = sa.MetaData()
            meta.reflect(bind=sync_conn)
            return meta

        src_meta = await src_conn.run_sync(_reflect)
        async with dst_engine.connect() as dst_conn:
            dst_meta = await dst_conn.run_sync(_reflect)

        missing = [name for name in COPY_ORDER if name not in dst_meta.tables]
        if missing:
            print(f"ERROR: target is missing tables {missing} — did the Alembic upgrade succeed?")
            return 1

        for name in COPY_ORDER:
            if name not in src_meta.tables:
                skipped[name] = "table absent in source (pre-feature database)"
                continue
            src_table = src_meta.tables[name]
            dst_table = dst_meta.tables[name]
            rows = (await src_conn.execute(sa.select(src_table))).mappings().all()
            for start in range(0, len(rows), CHUNK_SIZE):
                chunk = [
                    {col.name: _coerce(col, row.get(col.name)) for col in dst_table.columns}
                    for row in rows[start : start + CHUNK_SIZE]
                ]
                stmt = pg_insert(dst_table).values(chunk).on_conflict_do_nothing()
                async with dst_engine.begin() as dst:
                    await dst.execute(stmt)
            copied[name] = len(rows)

    print("\n== Copy report ==")
    for name in COPY_ORDER:
        if name in skipped:
            print(f"  {name:<22} SKIPPED ({skipped[name]})")
        else:
            print(f"  {name:<22} {copied[name]:>6} rows read from source")

    # Verify: target must hold every source row (it may hold more if the
    # target was not empty when the copy started).
    ok = True
    print("\n== Verification ==")
    async with src_engine.connect() as src_conn, dst_engine.connect() as dst_conn:
        for name in COPY_ORDER:
            if name not in src_meta.tables:
                continue
            src_count = (await src_conn.execute(
                sa.select(sa.func.count()).select_from(src_meta.tables[name])
            )).scalar_one()
            dst_count = (await dst_conn.execute(
                sa.select(sa.func.count()).select_from(dst_meta.tables[name])
            )).scalar_one()
            status = "OK" if dst_count >= src_count else "MISMATCH"
            ok = ok and dst_count >= src_count
            print(f"  {name:<22} source {src_count:>6} / target {dst_count:>6}  {status}")

    await src_engine.dispose()
    await dst_engine.dispose()
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_source = DB_PATH if DB_PATH != ":memory:" else str(backend_root / "data" / "aura.db")
    parser.add_argument(
        "--source",
        default=default_source,
        type=Path,
        help=f"SQLite file to copy from (default: {default_source})",
    )
    args = parser.parse_args()

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL must be set to the Postgres target, e.g.")
        print("  postgresql+asyncpg://aura_user:pw@postgres:5432/aura")
        return 2
    if not DATABASE_URL.startswith("postgresql"):
        print(f"ERROR: DATABASE_URL must be a postgresql:// URL, got: {DATABASE_URL}")
        return 2
    if not args.source.exists():
        print(f"ERROR: source SQLite file not found: {args.source}")
        return 2

    # Create/upgrade the target schema first. env.py resolves the same
    # DATABASE_URL and drives the async engine internally.
    from alembic import command
    from alembic.config import Config

    print(f"Bringing target {DATABASE_URL.rsplit('@', 1)[-1]} to Alembic head "
          f"(source: {args.source})")
    command.upgrade(Config(str(backend_root / "alembic.ini")), "head")

    return asyncio.run(_copy(args.source))


if __name__ == "__main__":
    sys.exit(main())
