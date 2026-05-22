import asyncio, json, os
import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from worker.tasks import resume_plan, STREAM_KEY

async_r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def ws_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    stream_key = STREAM_KEY.format(job_id=job_id)
    last_id = "0"   # read from beginning — replay all messages on reconnect

    async def forward():
        """Read from Redis Stream and push to WebSocket client."""
        nonlocal last_id
        try:
            while True:
                entries = await async_r.xread({stream_key: last_id}, block=5000, count=10)
                for _, messages in (entries or []):
                    for msg_id, fields in messages:
                        last_id = msg_id
                        await websocket.send_text(fields[b"data"].decode())
        except WebSocketDisconnect:
            pass

    async def receive():
        """Receive hitl_response from client and dispatch to Celery."""
        try:
            while True:
                data = await websocket.receive_text()
                payload = json.loads(data)
                if payload.get("type") == "hitl_response":
                    resume_plan.delay(
                        job_id,
                        payload["text"],
                        payload["interrupt_id"],
                    )
        except WebSocketDisconnect:
            pass

    await asyncio.gather(forward(), receive())
