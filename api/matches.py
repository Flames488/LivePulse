
from fastapi import APIRouter
from services.football_api_service import get_live_epl_matches

router = APIRouter()

@router.get("/live")
def live_matches():
    return get_live_epl_matches()
