"""
LLM Tool 接口 - 国内机票查询

用法（直接调用）:
    from tool import run
    result = run(departure="上海", arrival="北京", date="2026-06-15")

用法（作为 LLM tool）:
    将 TOOL_DEFINITION 注册到你的 agent，
    收到 tool_call 后调用 run(**tool_call["arguments"])
"""

import asyncio
import sys
from datetime import datetime
from typing import Literal

from playwright.async_api import async_playwright

from scraper import fetch_ctrip, fetch_ly, CITY_CODES

# ─────────────────────────────────────────────
# Tool Schema（适用于 OpenAI / Anthropic 格式）
# ─────────────────────────────────────────────

TOOL_DEFINITION = {
    "name": "search_flights",
    "description": (
        "查询国内直飞航班的实时价格，同时抓取携程和同程旅行两个平台的数据并去重合并。"
        "返回按起飞时间排序的航班列表，每条包含航班号、起飞/到达时间、机场、最低价格。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "departure": {
                "type": "string",
                "description": "出发城市，中文名称，如：上海、北京、广州、成都",
            },
            "arrival": {
                "type": "string",
                "description": "到达城市，中文名称，如：北京、上海、深圳、杭州",
            },
            "date": {
                "type": "string",
                "description": "出发日期，格式 YYYY-MM-DD，如：2026-06-15",
            },
            "platforms": {
                "type": "array",
                "items": {"type": "string", "enum": ["ctrip", "ly"]},
                "description": "查询平台，ctrip=携程，ly=同程旅行，默认两者都查",
                "default": ["ctrip", "ly"],
            },
        },
        "required": ["departure", "arrival", "date"],
    },
}


# ─────────────────────────────────────────────
# 核心执行逻辑
# ─────────────────────────────────────────────

Flight = dict  # {flight, dep, dep_ap, arr, arr_ap, price}


async def _run_async(
    departure: str,
    arrival: str,
    date: str,
    platforms: list[str],
) -> dict:
    if departure not in CITY_CODES:
        return {"status": "error", "message": f"不支持的出发城市：{departure}，支持城市：{sorted(CITY_CODES)}"}
    if arrival not in CITY_CODES:
        return {"status": "error", "message": f"不支持的到达城市：{arrival}，支持城市：{sorted(CITY_CODES)}"}

    results: dict[str, list[Flight]] = {}
    errors: dict[str, str] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = {}
        if "ctrip" in platforms:
            tasks["ctrip"] = asyncio.create_task(fetch_ctrip(browser, departure, arrival, date))
        if "ly" in platforms:
            tasks["ly"] = asyncio.create_task(fetch_ly(browser, departure, arrival, date))

        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                errors[name] = str(e)
                results[name] = []

        await browser.close()

    # 合并两平台数据：航班号+起飞时间+到达时间相同即为同一班次，保留最低价
    merged: dict[tuple, Flight] = {}
    for platform, flights in results.items():
        for f in flights:
            k = (f["flight"], f["dep"], f["arr"])
            entry = {**f, "source": platform}
            if k not in merged or f["price"] < merged[k]["price"]:
                merged[k] = entry

    all_flights = sorted(merged.values(), key=lambda x: x["dep"])
    min_price = min((f["price"] for f in all_flights), default=None)
    cheapest = [f for f in all_flights if f["price"] == min_price] if min_price else []

    return {
        "status": "success",
        "query": {
            "departure": departure,
            "arrival": arrival,
            "date": date,
            "platforms": platforms,
        },
        "results": {k: v for k, v in results.items()},
        "merged": all_flights,
        "summary": {
            "total_flights": len(all_flights),
            "platform_counts": {k: len(v) for k, v in results.items()},
            "min_price": min_price,
            "cheapest_flights": cheapest,
            "errors": errors,
        },
    }


def run(
    departure: str,
    arrival: str,
    date: str,
    platforms: list[str] | None = None,
) -> dict:
    """
    同步调用入口，阻塞直到结果返回。

    Args:
        departure: 出发城市（中文），如 "上海"
        arrival:   到达城市（中文），如 "北京"
        date:      出发日期，格式 YYYY-MM-DD
        platforms: 查询平台列表，可选 "ctrip"、"ly"，默认两者都查

    Returns:
        dict，结构见 TOOL_DEFINITION 描述，主要字段：
          - status:   "success" | "error"
          - merged:   合并后的航班列表（按起飞时间升序，同时段保留最低价）
          - results:  各平台原始结果
          - summary:  统计摘要（总数、最低价、最便宜航班等）
    """
    return asyncio.run(_run_async(departure, arrival, date, platforms or ["ctrip", "ly"]))


# ─────────────────────────────────────────────
# 命令行快速测试
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import json

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    result = run("上海", "北京", "2026-06-15")
    if result["status"] == "success":
        s = result["summary"]
        print(f"共 {s['total_flights']} 班  最低 ¥{s['min_price']}")
        print(f"携程 {s['platform_counts'].get('ctrip', 0)} 条  同程 {s['platform_counts'].get('ly', 0)} 条")
        print()
        for f in result["merged"]:
            print(f"  {f['flight']:<10} {f['dep']} {f.get('dep_ap',''):<8} → "
                  f"{f['arr']} {f.get('arr_ap',''):<8}  ¥{f['price']:>5}  [{f['source']}]")
    else:
        print(f"错误: {result['message']}")
