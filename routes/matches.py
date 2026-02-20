
from fastapi import APIRouter
router = APIRouter(prefix="/matches")

@router.get("/")
def list_matches():
    return {"matches": []}
