"""
LangGraph Studio 入口。

与生产图的区别：
- 不传 checkpointer（Studio 平台自己管持久化）
- tools 在模块加载时预注入，Studio 不会注入 configurable["tools"]
"""
from agent.graph import build_compiled_graph
from agent.tools_container import build_tools

_tools = build_tools()


def _inject_tools(fn):
    async def _wrapped(state, config):
        merged = {**config, "configurable": {**config.get("configurable", {}), "tools": _tools}}
        return await fn(state, merged)
    _wrapped.__name__ = getattr(fn, "__name__", "node")
    return _wrapped


graph = build_compiled_graph(node_wrapper=_inject_tools)
