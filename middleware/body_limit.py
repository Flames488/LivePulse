from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size=1_000_000):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request, call_next):
        body = await request.body()
        if len(body) > self.max_size:
            return JSONResponse({"error": "Request too large"}, 413)
        return await call_next(request)
