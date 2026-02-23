from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect
from pydantic import BaseModel, Field
from slowapi.middleware import SlowAPIMiddleware
from typing import Any

from config_validator import validate_env

validate_env()

from api import websocket as ws_routes
from api.matches import router as api_match_router
from api.predictions import router as api_prediction_router
from middleware.error_handler import add_exception_handlers
from middleware.security import add_security_middleware
from routes.health import router as health_router
from core.rate_limit import limiter
from core.sentry_config import init_sentry
from core.logging_config import setup_logging
from middleware.body_limit import BodySizeLimitMiddleware
from prediction_engine import calculate_points
from routes import admin, leaderboard, matches, predictions
from supabase import create_client
from websocket import manager

# ---------------------------------------------------------------------------
# Logging — configure first so every subsequent module can emit structured logs
# ---------------------------------------------------------------------------

setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

init_sentry()

# ---------------------------------------------------------------------------
# Environment / Config
# ---------------------------------------------------------------------------

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
FOOTBALL_API_KEY: str = os.environ["FOOTBALL_API_KEY"]
ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")
API_ENV: str = os.getenv("API_ENV", "production")
API_VERSION: str = "1.0.0"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PredictionRequest(BaseModel):
    """Payload for validating a user's prediction against an actual event."""

    prediction: dict[str, Any] = Field(..., description="The user's submitted prediction.")
    event: dict[str, Any] = Field(..., description="The actual event outcome data.")
    streak: int = Field(default=0, ge=0, description="Current correct-prediction streak.")


class PredictionResponse(BaseModel):
    points: int
    correct: bool


# ---------------------------------------------------------------------------
# Application Lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    logger.info(
        "LivePulse API starting",
        extra={"environment": API_ENV, "version": API_VERSION},
    )
    yield
    logger.info("LivePulse API shutting down")


# ---------------------------------------------------------------------------
# Application Factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    application = FastAPI(
        title="LivePulse API",
        description=(
            "Real-time football predictions, leaderboards, and live match data. "
            "WebSocket connections are available per match."
        ),
        version=API_VERSION,
        docs_url="/docs" if API_ENV != "production" else None,
        redoc_url="/redoc" if API_ENV != "production" else None,
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------

    application.state.limiter = limiter
    application.add_middleware(SlowAPIMiddleware)

    # -------------------------------------------------------------------
    # Middleware  (outermost → innermost)
    # -------------------------------------------------------------------

    # Hard cap on incoming request body size — must be added before other
    # middleware that reads the body so it can reject oversized payloads early.
    application.add_middleware(BodySizeLimitMiddleware)

    # Security headers (CSP, HSTS, etc.) from the backend middleware module.
    add_security_middleware(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Request timing and correlation-ID propagation.
    @application.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        start = time.perf_counter()
        correlation_id = request.headers.get("X-Correlation-ID", "-")
        logger.debug(
            "Incoming request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
            },
        )
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1_000
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        logger.debug(
            "Request completed",
            extra={
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "correlation_id": correlation_id,
            },
        )
        return response

    # -------------------------------------------------------------------
    # Exception Handlers
    # -------------------------------------------------------------------

    add_exception_handlers(application)

    # -------------------------------------------------------------------
    # Routers
    # -------------------------------------------------------------------

    # System
    application.include_router(health_router, tags=["System"])

    # WebSocket
    application.include_router(ws_routes.router, tags=["WebSocket"])

    # Legacy unversioned routes (kept for backwards compatibility)
    application.include_router(matches.router, prefix="/matches", tags=["Matches"])
    application.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
    application.include_router(leaderboard.router, prefix="/leaderboard", tags=["Leaderboard"])
    application.include_router(admin.router, prefix="/admin", tags=["Admin"])

    # v1 versioned routes
    application.include_router(api_match_router, prefix="/v1/matches", tags=["Matches v1"])
    application.include_router(api_prediction_router, prefix="/v1/predictions", tags=["Predictions v1"])

    # -------------------------------------------------------------------
    # Core Routes
    # -------------------------------------------------------------------

    @application.get("/", tags=["System"], summary="Root liveness check")
    def root() -> dict[str, str]:
        """Returns a quick confirmation that the API process is alive."""
        return {"status": "LivePulse API running"}

    @application.get("/health", tags=["System"], summary="Health check")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post(
        "/validate_prediction",
        response_model=PredictionResponse,
        tags=["Predictions"],
        summary="Validate a prediction against a real event outcome",
        status_code=status.HTTP_200_OK,
    )
    async def validate_prediction(body: PredictionRequest) -> PredictionResponse:
        """
        Computes points awarded for a prediction and whether it was correct,
        factoring in the user's current streak multiplier.
        """
        try:
            points, correct = calculate_points(body.prediction, body.event, body.streak)
        except Exception as exc:
            logger.exception("Failed to calculate points")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Prediction calculation error: {exc}",
            ) from exc

        logger.info(
            "Prediction validated",
            extra={"points": points, "correct": correct, "streak": body.streak},
        )
        return PredictionResponse(points=points, correct=bool(correct))

    # -------------------------------------------------------------------
    # WebSocket endpoint
    # -------------------------------------------------------------------

    @application.websocket("/ws/{match_id}")
    async def websocket_endpoint(websocket: WebSocket, match_id: str) -> None:
        """
        Persistent WebSocket connection for live match updates.
        Clients subscribe to a specific match by its ID.
        """
        await manager.connect(websocket, match_id)
        logger.info("WebSocket connected", extra={"match_id": match_id})
        try:
            while True:
                message = await websocket.receive_text()
                logger.debug(
                    "WebSocket message received",
                    extra={"match_id": match_id, "message": message},
                )
        except WebSocketDisconnect:
            manager.disconnect(websocket, match_id)
            logger.info("WebSocket disconnected", extra={"match_id": match_id})
        except Exception:
            manager.disconnect(websocket, match_id)
            logger.exception("Unexpected WebSocket error", extra={"match_id": match_id})

    return application


# ---------------------------------------------------------------------------
# App Instance
# ---------------------------------------------------------------------------

app = create_app()

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=API_ENV != "production",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True,
    )