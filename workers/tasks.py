
from celery_app import celery

@celery.task
def poll_match_events():
    # Poll football API and persist events
    pass
