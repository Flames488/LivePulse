from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

@asynccontextmanager
async def atomic(session: AsyncSession):
    """
    Ensures atomic DB transaction.
    Prevents partial writes during scoring updates.
    """
    try:
        async with session.begin():
            yield
    except Exception:
        await session.rollback()
        raise
