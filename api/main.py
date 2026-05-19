import asyncio
import json
import os
import uuid
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph

app = FastAPI(title="Smart Travel Agent API")
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
_graph = build_graph()


class PlanRequest(BaseModel):
    destination: str
    origin: str
    duration_days: int
    travelers: int = 1
    transport_mode: str = "mixed"
    difficulty_level: str = "medium"
    interests: list[str] = []
    depart_date: Optional[str] = None


async def _run_plan(job_id: str, req: PlanRequest):
    _redis.set(f"job:{job_id}:status", json.dumps({"status": "running", "progress": "starting"}))
    try:
        state = {
            **req.model_dump(),
            "errors": [],
            "warnings": [],
            "job_id": job_id,
        }
        result = await _graph.ainvoke(state)
        _redis.setex(
            f"job:{job_id}:status",
            7200,
            json.dumps({"status": "done", "result": result}),
        )
    except Exception as e:
        _redis.setex(
            f"job:{job_id}:status",
            7200,
            json.dumps({"status": "error", "error": str(e)}),
        )


@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    _redis.set(f"job:{job_id}:status", json.dumps({"status": "pending", "progress": "queued"}))
    asyncio.create_task(_run_plan(job_id, req))
    return {"job_id": job_id, "status": "pending"}


@app.get("/plans/{job_id}")
async def get_plan(job_id: str):
    raw = _redis.get(f"job:{job_id}:status")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    data = json.loads(raw)
    # Read fine-grained progress from nodes
    progress_raw = _redis.get(f"job:{job_id}:progress")
    if progress_raw:
        data["progress"] = progress_raw.decode()
    return data
