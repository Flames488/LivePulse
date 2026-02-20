
from fastapi import APIRouter
from prediction_engine import calculate_points

router = APIRouter(prefix="/predictions")

@router.post("/validate")
def validate(prediction: str, event: str):
    points = calculate_points(event, prediction)
    return {"points_awarded": points}
