
from fastapi import APIRouter

router = APIRouter(prefix="/leaderboard")

@router.get("/global")
def global_board():
    return {"leaderboard": []}
