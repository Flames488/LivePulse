
from celery import Celery
import os

celery = Celery(
    "livepulse",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)
