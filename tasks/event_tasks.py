
from backend.core.celery_app import celery
from backend.integrations.api_football import fetch_live_events

@celery.task
def poll_match_events(match_id: int):
    return fetch_live_events(match_id)


@celery.task
def background_job(data):
    return {"processed": data}
