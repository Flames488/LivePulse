import time
import platform
import psutil
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/health", tags=["Health"])

_START_TIME = time.time()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ComponentHealth(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class SystemMetrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_percent: float
    python_version: str
    os: str


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    uptime_seconds: float
    timestamp: str
    components: dict[str, ComponentHealth]
    system: SystemMetrics


# ── Dependency Checks ────────────────────────────────────────────────────────

async def check_database() -> ComponentHealth:
    """Ping the database. Replace the sleep with: await session.execute('SELECT 1')"""
    start = time.perf_counter()
    try:
        await asyncio.sleep(0.005)  # TODO: replace with real DB ping
        latency_ms = (time.perf_counter() - start) * 1000
        return ComponentHealth(status="healthy", latency_ms=round(latency_ms, 2))
    except Exception as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


async def check_cache() -> ComponentHealth:
    """Ping the cache layer. Replace the sleep with: await redis.ping()"""
    start = time.perf_counter()
    try:
        await asyncio.sleep(0.002)  # TODO: replace with real cache ping
        latency_ms = (time.perf_counter() - start) * 1000
        return ComponentHealth(status="healthy", latency_ms=round(latency_ms, 2))
    except Exception as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


async def check_external_api() -> ComponentHealth:
    """Probe a downstream HTTP service. Replace the sleep with a real HTTP request."""
    start = time.perf_counter()
    try:
        await asyncio.sleep(0.010)  # TODO: replace with real HTTP probe
        latency_ms = (time.perf_counter() - start) * 1000
        return ComponentHealth(status="healthy", latency_ms=round(latency_ms, 2))
    except Exception as exc:
        return ComponentHealth(status="unhealthy", detail=str(exc))


def get_system_metrics() -> SystemMetrics:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return SystemMetrics(
        cpu_percent=psutil.cpu_percent(interval=None),
        memory_percent=mem.percent,
        memory_available_mb=round(mem.available / 1_048_576, 1),
        disk_percent=disk.percent,
        python_version=platform.python_version(),
        os=platform.system(),
    )


def _aggregate_status(components: dict[str, ComponentHealth]) -> str:
    statuses = {c.status for c in components.values()}
    if "unhealthy" in statuses:
        return "unhealthy"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "",
    summary="Full health check",
    response_model=HealthResponse,
    responses={
        200: {"description": "Service is healthy or degraded"},
        503: {"description": "One or more components are unhealthy"},
    },
)
async def health_check(
    version: str = "1.0.0",
    environment: str = "production",
) -> JSONResponse:
    """
    Runs all component checks concurrently and returns a rich status payload.
    Responds with **200** when healthy or degraded, **503** when unhealthy.
    """
    db, cache, ext_api = await asyncio.gather(
        check_database(),
        check_cache(),
        check_external_api(),
    )

    components: dict[str, ComponentHealth] = {
        "database": db,
        "cache": cache,
        "external_api": ext_api,
    }

    overall = _aggregate_status(components)

    payload = HealthResponse(
        status=overall,
        version=version,
        environment=environment,
        uptime_seconds=round(time.time() - _START_TIME, 2),
        timestamp=datetime.now(timezone.utc).isoformat(),
        components=components,
        system=get_system_metrics(),
    )

    http_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if overall == "unhealthy"
        else status.HTTP_200_OK
    )
    return JSONResponse(content=payload.model_dump(), status_code=http_status)


@router.get(
    "/live",
    summary="Liveness probe",
    description="Lightweight Kubernetes liveness probe — confirms the process is running.",
)
async def liveness() -> dict:
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Kubernetes readiness probe — confirms the service can handle traffic.",
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"},
    },
)
async def readiness() -> JSONResponse:
    db = await check_database()

    if db.status == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": "database unavailable"},
        )

    return JSONResponse(
        content={"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}
    )