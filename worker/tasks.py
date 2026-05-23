import asyncio, functools, json, logging, os, uuid
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

PROGRESS_MESSAGES = {
    "parse_input":    "正在解析出行需求...",
    "discover_pois":  "正在搜索目的地景点...",
    "scrape_flights": "正在查询航班价格...",
    "plan_itinerary": "正在规划行程方案（约 1-2 分钟）...",
    "compose_output": "正在整理最终行程...",
}


def make_node_wrapper(job_id: str):
    def wrapper(fn):
        node_name = fn.__module__.split(".")[-1]
        msg = PROGRESS_MESSAGES.get(node_name)

        @functools.wraps(fn)
        async def wrapped(state, config):
            # Only emit for compute nodes (not in PROGRESS_MESSAGES → msg is None).
            # HITL nodes (collect_intent, human_review) are intentionally absent.
            # LangGraph checkpointing ensures completed compute nodes never re-run
            # on resume, so no double-fire risk for this graph topology.
            if msg:
                _emit(job_id, {"type": "progress", "node": node_name, "message": msg})
            return await fn(state, config)

        return wrapped
    return wrapper


def _build_config(job_id: str) -> dict:
    return {
        "configurable": {"thread_id": job_id, "tools": build_tools()},
        "run_name": f"travel_plan/{job_id}",
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
            graph = build_compiled_graph(checkpointer, node_wrapper=make_node_wrapper(job_id))
            return await graph.ainvoke(initial_state, config=_build_config(job_id))

    try:
        _handle_result(job_id, asyncio.run(_run()))
    except Exception as exc:
        logger.exception("[job=%s] run_plan failed", job_id)
        try:
            _emit(job_id, {"type": "error", "message": f"规划失败，请稍后重试（{type(exc).__name__}）"})
        except Exception:
            logger.warning("[job=%s] error emit failed", job_id)
        raise


@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str, interrupt_id: str):
    lock_key = f"job:{job_id}:resume:{interrupt_id}"
    if not r.set(lock_key, "1", nx=True, ex=300):
        return

    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer, node_wrapper=make_node_wrapper(job_id))
            return await graph.ainvoke(
                Command(resume={"text": user_text}), config=_build_config(job_id)
            )

    try:
        _handle_result(job_id, asyncio.run(_run()))
    except Exception as exc:
        logger.exception("[job=%s] resume_plan failed", job_id)
        try:
            _emit(job_id, {"type": "error", "message": f"规划失败，请稍后重试（{type(exc).__name__}）"})
        except Exception:
            logger.warning("[job=%s] error emit failed", job_id)
        raise
