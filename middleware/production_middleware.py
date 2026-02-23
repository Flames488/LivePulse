from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
import asyncio

class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=10)
        except asyncio.TimeoutError:
            return JSONResponse({"error": "Request timeout"}, status_code=504)