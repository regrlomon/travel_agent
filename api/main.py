import asyncio, json, os, uuid
from typing import Optional, AsyncGenerator
import redis.asyncio as aioredis
import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from worker.tasks import run_plan, resume_plan, STREAM_KEY

app = FastAPI(title="Smart Travel Agent API")
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
_async_redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


class PlanRequest(BaseModel):
    destination: str
    origin: str
    duration_days: int
    travelers: int = 1
    transport_mode: str = "mixed"
    difficulty_level: str = "medium"
    interests: list[str] = []
    depart_date: Optional[str] = None


class ReplyRequest(BaseModel):
    text: str
    interrupt_id: str


@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    run_plan.delay(job_id, req.model_dump())
    return {"job_id": job_id, "status": "pending"}


@app.post("/plans/{job_id}/reply", status_code=202)
async def reply_plan(job_id: str, body: ReplyRequest):
    """HITL reply: user sends response, triggers graph resume via Celery."""
    resume_plan.delay(job_id, body.text, body.interrupt_id)
    return {"status": "ok"}


@app.get("/plans/{job_id}/events")
async def plan_events(job_id: str):
    """SSE endpoint: stream Redis Stream messages to frontend."""
    stream_key = STREAM_KEY.format(job_id=job_id)

    async def generator() -> AsyncGenerator[str, None]:
        last_id = "0"
        while True:
            entries = await _async_redis.xread({stream_key: last_id}, block=5000, count=10)
            for _, messages in (entries or []):
                for msg_id, fields in messages:
                    last_id = msg_id
                    data = fields[b"data"].decode()
                    yield f"data: {data}\n\n"
                    if json.loads(data).get("type") == "done":
                        return

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/plans/{job_id}/state")
async def get_plan_state(job_id: str):
    """Reconnect: return last message in stream for state recovery."""
    key = STREAM_KEY.format(job_id=job_id)
    entries = _redis.xrevrange(key, count=1)
    if entries:
        _, fields = entries[0]
        return json.loads(fields[b"data"])
    raise HTTPException(status_code=404, detail="No stream data for this job")
