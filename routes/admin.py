
from fastapi import APIRouter, Depends
from auth import verify_jwt

router = APIRouter()

@router.post("/add-match")
def add_match(user=Depends(verify_jwt)):
    if user.get("role") != "admin":
        return {"error": "Not authorized"}
    return {"message": "Match added"}
