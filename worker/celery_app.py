import os
from celery import Celery

celery_app = Celery(
    "travel_agent",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_expires = 7200
