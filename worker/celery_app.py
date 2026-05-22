import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "travel_agent",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["worker.tasks"],
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_expires = 7200
# Windows uses 'spawn' (not 'fork'), so child processes can't inherit
# Celery's _loc optimization cache. solo pool avoids subprocess spawning entirely.
celery_app.conf.worker_pool = "solo"
