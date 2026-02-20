
from datetime import datetime, timezone

ROUND_SECONDS = 180

def is_prediction_allowed(round_start: datetime):
    now = datetime.now(timezone.utc)
    return (now - round_start).total_seconds() < ROUND_SECONDS
