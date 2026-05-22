import json, os, subprocess, sys, uuid
from contextlib import asynccontextmanager
from typing import Optional
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from worker.tasks import run_plan, STREAM_KEY

_worker_process: subprocess.Popen | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_process
    _worker_process = subprocess.Popen([
        sys.executable, "-m", "celery",
        "-A", "worker.celery_app", "worker",
        "--loglevel=info", "--concurrency=2",
    ])
    yield
    if _worker_process:
        _worker_process.terminate()
        _worker_process.wait()


app = FastAPI(title="Smart Travel Agent API", lifespan=lifespan)
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


class PlanRequest(BaseModel):
    destination: str
    origin: str
    duration_days: int
    travelers: int = 1
    transport_mode: str = "mixed"
    difficulty_level: str = "medium"
    interests: list[str] = []
    depart_date: Optional[str] = None


@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    run_plan.delay(job_id, req.model_dump())
    return {"job_id": job_id, "status": "pending"}


@app.get("/plans/{job_id}/state")
async def get_plan_state(job_id: str):
    """Reconnect endpoint: return last message in job stream for state recovery."""
    key = STREAM_KEY.format(job_id=job_id)
    entries = _redis.xrevrange(key, count=1)
    if entries:
        _, fields = entries[0]
        return json.loads(fields[b"data"])
    raise HTTPException(status_code=404, detail="No stream data for this job")


# Register WebSocket endpoint
from api.websocket import ws_endpoint  # noqa: E402
app.add_api_websocket_route("/ws/{job_id}", ws_endpoint)
