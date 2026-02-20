from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Prevent duplicate scoring / replay attacks
    Requires Idempotency-Key header
    """

    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("Idempotency-Key")

        if key:
            client = redis.from_url(REDIS_URL)

            exists = await client.get(key)
            if exists:
                await client.close()
                raise HTTPException(status_code=409, detail="Duplicate request detected")

            await client.set(key, "1", ex=60)
            await client.close()

        response = await call_next(request)
        return response
