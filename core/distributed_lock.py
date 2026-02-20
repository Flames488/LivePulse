import os
import asyncio
import redis.asyncio as redis
from contextlib import asynccontextmanager

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

@asynccontextmanager
async def acquire_lock(key: str, timeout: int = 10):
    """
    Distributed Redis lock for multi-instance safety.
    Prevents race conditions during scoring & prediction locking.
    """
    client = redis.from_url(REDIS_URL)
    lock = client.lock(key, timeout=timeout)

    acquired = await lock.acquire(blocking=True)
    if not acquired:
        raise Exception("Could not acquire distributed lock")

    try:
        yield
    finally:
        await lock.release()
        await client.close()
