import asyncio, json, logging, os, uuid
import redis as _redis
from langsmith import Client as LangSmithClient

logger = logging.getLogger(__name__)
from langgraph.types import Command
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from agent.graph import build_compiled_graph
from agent.tools_container import build_tools
from worker.celery_app import celery_app

r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
STREAM_KEY = "job:{job_id}:stream"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LANGSMITH_DATASET = "travel-agent-traces"
_ls_client = LangSmithClient()


def _build_config(job_id: str) -> dict:
    return {
        "configurable": {"thread_id": job_id, "tools": build_tools()},
        "metadata": {"job_id": job_id},
        "tags": [os.getenv("LANGCHAIN_TAGS", "env:dev")],
    }


def _emit(job_id: str, payload: dict):
    key = STREAM_KEY.format(job_id=job_id)
    r.xadd(key, {"data": json.dumps(payload, ensure_ascii=False)})
    r.expire(key, 7200)


def _auto_add_to_dataset(job_id: str, result: dict):
    try:
        try:
            dataset = _ls_client.read_dataset(dataset_name=LANGSMITH_DATASET)
        except Exception:
            dataset = _ls_client.create_dataset(LANGSMITH_DATASET)

        _ls_client.create_example(
            inputs={
                "destination":   result.get("destination"),
                "origin":        result.get("origin"),
                "duration_days": result.get("duration_days"),
                "interests":     result.get("interests", []),
            },
            outputs={
                "itineraries_count": len(result.get("itineraries", [])),
                "warnings":          result.get("warnings", []),
                "errors":            result.get("errors", []),
            },
            metadata={"job_id": job_id},
            dataset_id=dataset.id,
        )
    except Exception:
        logger.warning("[job=%s] LangSmith dataset write failed, skipping", job_id)


def _handle_result(job_id: str, result: dict):
    logger.info("[job=%s] LLM result: %s", job_id, json.dumps(result, ensure_ascii=False, default=str))
    interrupts = result.get("__interrupt__")
    if interrupts:
        interrupt_id = str(uuid.uuid4())
        _emit(job_id, {
            "type": "hitl_request",
            "interrupt_id": interrupt_id,
            "data": interrupts[0].value,
        })
    else:
        _emit(job_id, {
            "type": "done",
            "result": {
                "status": result.get("status"),
                "itineraries": result.get("itineraries", []),
                "flights_comparison": result.get("flights_comparison", []),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
            },
        })
        if not result.get("errors"):
            _auto_add_to_dataset(job_id, result)


@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, initial_state: dict):
    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer)
            return await graph.ainvoke(initial_state, config=_build_config(job_id))

    _handle_result(job_id, asyncio.run(_run()))


@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str, interrupt_id: str):
    lock_key = f"job:{job_id}:resume:{interrupt_id}"
    if not r.set(lock_key, "1", nx=True, ex=300):
        return

    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer)
            return await graph.ainvoke(
                Command(resume={"text": user_text}), config=_build_config(job_id)
            )

    _handle_result(job_id, asyncio.run(_run()))
