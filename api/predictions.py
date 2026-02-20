
from fastapi import APIRouter, HTTPException
from services.prediction_lock import is_prediction_allowed
from datetime import datetime

router = APIRouter()

@router.post("/")
def create_prediction(round_start: datetime):
    if not is_prediction_allowed(round_start):
        raise HTTPException(status_code=403, detail="Prediction locked")
    return {"status": "accepted"}
