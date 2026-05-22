import os
from tools.amap import AmapClient
from tools.tavily import TavilyClient
from tools.xhs_tool import XhsClient
from tools.flight_tool.tool import FlightClient


def build_tools(overrides: dict | None = None) -> dict:
    defaults = {
        "amap":   AmapClient(api_key=os.getenv("AMAP_API_KEY", "")),
        "tavily": TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "")),
        "xhs":    XhsClient(),
        "flight": FlightClient(),
    }
    return {**defaults, **(overrides or {})}
