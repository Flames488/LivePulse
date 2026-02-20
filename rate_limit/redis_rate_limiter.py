
import redis
import os
from fastapi import HTTPException

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.Redis.from_url(REDIS_URL)

def rate_limit(key: str, limit: int = 20, window: int = 60):
    current = r.get(key)
    if current and int(current) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    pipe = r.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, window)
    pipe.execute()
