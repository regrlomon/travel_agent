import asyncio, json, os, uuid
import redis as _redis
from langgraph.types import Command
from langgraph.checkpoint.redis import RedisSaver

from agent.graph import build_compiled_graph
from agent.tools_container import build_tools
from worker.celery_app import celery_app

r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
STREAM_KEY = "job:{job_id}:stream"


def _build_config(job_id: str) -> dict:
    return {"configurable": {"thread_id": job_id, "tools": build_tools()}}


def _emit(job_id: str, payload: dict):
    """Write to Redis Stream. Stream has 2h TTL and persists messages for replay."""
    key = STREAM_KEY.format(job_id=job_id)
    r.xadd(key, {"data": json.dumps(payload, ensure_ascii=False)})
    r.expire(key, 7200)


def _handle_result(job_id: str, result: dict):
    """Inspect ainvoke return value — emit hitl_request if interrupted, done if complete."""
    interrupts = result.get("__interrupt__")
    if interrupts:
        interrupt_id = str(uuid.uuid4())
        _emit(job_id, {
            "type": "hitl_request",
            "interrupt_id": interrupt_id,
            "data": interrupts[0].value,
        })
    else:
        _emit(job_id, {"type": "done", "result": result})


@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, request_data: dict):
    initial_state = {**request_data, "errors": [], "warnings": [], "job_id": job_id}
    with RedisSaver.from_conn_string(os.getenv("REDIS_URL", "redis://localhost:6379/0")) as checkpointer:
        checkpointer.setup()
        graph = build_compiled_graph(checkpointer)
        result = asyncio.run(graph.ainvoke(initial_state, config=_build_config(job_id)))
    _handle_result(job_id, result)


@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str, interrupt_id: str):
    """Resume a graph that was paused at interrupt(). Idempotent via Redis NX lock."""
    lock_key = f"job:{job_id}:resume:{interrupt_id}"
    if not r.set(lock_key, "1", nx=True, ex=300):
        return
    with RedisSaver.from_conn_string(os.getenv("REDIS_URL", "redis://localhost:6379/0")) as checkpointer:
        checkpointer.setup()
        graph = build_compiled_graph(checkpointer)
        result = asyncio.run(
            graph.ainvoke(Command(resume={"text": user_text}), config=_build_config(job_id))
        )
    _handle_result(job_id, result)
