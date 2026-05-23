"""
单节点回放工具 — 利用现有 Redis checkpointer，无需从头重跑。

用法:
  # 1. 列出某次运行的所有 checkpoint（看哪个节点失败）
  python scripts/debug_replay.py --job-id <job_id> --list

  # 2. 从指定节点重新开始跑（节点之前的 state 原样保留）
  python scripts/debug_replay.py --job-id <job_id> --from-node plan_itinerary

  # 3. 把某个节点入口的 state 导出成 JSON（用于写单测 fixture）
  python scripts/debug_replay.py --job-id <job_id> --dump-state plan_itinerary > /tmp/state.json

环境变量:
  REDIS_URL  默认 redis://localhost:6379/0
"""
import asyncio
import argparse
import json
import os
import sys
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from agent.graph import build_compiled_graph
from agent.tools_container import build_tools

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
NODES = [
    "collect_intent", "parse_input", "discover_pois",
    "scrape_flights", "plan_itinerary", "human_review", "compose_output",
]


def _make_config(job_id: str, extra: dict | None = None) -> dict:
    cfg: dict = {"configurable": {"thread_id": job_id, "tools": build_tools()}}
    if extra:
        cfg["configurable"].update(extra)
    return cfg


async def _get_checkpoint_before(graph, base_config: dict, node_name: str):
    """找到 next 包含 node_name 的最新 checkpoint，即该节点运行前的快照。"""
    async for snap in graph.aget_state_history(base_config):
        if node_name in (snap.next or ()):
            return snap
    return None


async def cmd_list(job_id: str):
    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as cp:
        await cp.asetup()
        graph = build_compiled_graph(cp)
        print(f"{'#':<4}  {'next node(s)':<28}  state keys")
        print("-" * 72)
        i = 0
        async for snap in graph.aget_state_history(_make_config(job_id)):
            next_label = ", ".join(snap.next) if snap.next else "(finished)"
            keys = ", ".join(snap.values.keys())
            ts = snap.created_at or ""
            print(f"{i:<4}  {next_label:<28}  {keys}")
            if ts:
                print(f"      created_at: {ts}")
            i += 1
        if i == 0:
            print("找不到该 job_id 的 checkpoint，请确认 job_id 是否正确。")


async def cmd_dump_state(job_id: str, node_name: str):
    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as cp:
        await cp.asetup()
        graph = build_compiled_graph(cp)
        snap = await _get_checkpoint_before(graph, _make_config(job_id), node_name)
        if snap is None:
            print(f"[error] 找不到 next={node_name!r} 的 checkpoint", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(snap.values, ensure_ascii=False, default=str, indent=2))


async def cmd_replay(job_id: str, node_name: str):
    async with AsyncRedisSaver.from_conn_string(REDIS_URL) as cp:
        await cp.asetup()
        graph = build_compiled_graph(cp)
        snap = await _get_checkpoint_before(graph, _make_config(job_id), node_name)
        if snap is None:
            print(f"[error] 找不到 next={node_name!r} 的 checkpoint，先用 --list 确认节点名", file=sys.stderr)
            sys.exit(1)

        print(f"[replay] 恢复到 next={list(snap.next)} 的快照，开始从 {node_name} 重跑...", file=sys.stderr)

        # 把 tools 合并进 checkpoint 自带的 config（保留 checkpoint_id / thread_id）
        resume_config = dict(snap.config)
        resume_config["configurable"] = {
            **snap.config.get("configurable", {}),
            "tools": build_tools(),
        }

        result = await graph.ainvoke(None, resume_config)
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="LangGraph 单节点回放工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--job-id", required=True, help="job_id（= Redis thread_id）")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出所有 checkpoint")
    group.add_argument(
        "--from-node",
        choices=NODES,
        metavar="NODE",
        help=f"从该节点重新开始执行。可选: {', '.join(NODES)}",
    )
    group.add_argument(
        "--dump-state",
        choices=NODES,
        metavar="NODE",
        help="把该节点入口的 state 导出为 JSON（可重定向到文件用作单测 fixture）",
    )

    args = parser.parse_args()

    if args.list:
        asyncio.run(cmd_list(args.job_id))
    elif args.from_node:
        asyncio.run(cmd_replay(args.job_id, args.from_node))
    elif args.dump_state:
        asyncio.run(cmd_dump_state(args.job_id, args.dump_state))


if __name__ == "__main__":
    main()
