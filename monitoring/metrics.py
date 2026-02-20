
from fastapi import APIRouter

router = APIRouter()

@router.get("/metrics")
def metrics():
    return {"requests": 0, "active_connections": 0}
