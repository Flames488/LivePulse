from datetime import datetime, timedelta
from sqlalchemy import text
from app.db.session import engine

LOCK_TIMEOUT = 60  # seconds


async def acquire_lock(name: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(text("""
        INSERT INTO job_locks(name, locked_at)
        VALUES (:name, now())
        ON CONFLICT (name)
        DO UPDATE SET locked_at = now()
        WHERE job_locks.locked_at < now() - interval '60 seconds'
        RETURNING name;
        """), {"name": name})

        return result.fetchone() is not None
