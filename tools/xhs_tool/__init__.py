import asyncio
from ._core import search_xhs, DEFAULT_COUNT, DEFAULT_CONTENT

# Anthropic tool use 格式定义
TOOL_DEFINITION = {
    "name": "search_xiaohongshu",
    "description": (
        "搜索小红书笔记，获取真实用户的旅游景点、美食、住宿等亲身体验内容。"
        "适合回答「XX 景点好不好玩」「XX 值不值得去」「XX 避坑指南」等问题。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "搜索关键词，例如：张家界旅游攻略、西湖值不值得去",
            },
            "count": {
                "type": "integer",
                "description": f"返回笔记数量，默认 {DEFAULT_COUNT}",
                "default": DEFAULT_COUNT,
            },
            "with_content": {
                "type": "boolean",
                "description": f"是否获取笔记正文，默认 {DEFAULT_CONTENT}",
                "default": DEFAULT_CONTENT,
            },
        },
        "required": ["keyword"],
    },
}


def handle_tool_call(tool_input: dict) -> list[dict]:
    """
    对接 Anthropic tool use 的 handler。

    用法:
        response = client.messages.create(tools=[TOOL_DEFINITION], ...)
        for block in response.content:
            if block.type == "tool_use" and block.name == "search_xiaohongshu":
                results = handle_tool_call(block.input)
    """
    return search_xhs(
        keyword=tool_input["keyword"],
        count=tool_input.get("count", DEFAULT_COUNT),
        with_content=tool_input.get("with_content", DEFAULT_CONTENT),
    )


__all__ = ["TOOL_DEFINITION", "handle_tool_call", "search_xhs", "XhsClient"]


class XhsClient:
    async def scrape_notes(self, keywords: list[str], max_notes_per_keyword: int = DEFAULT_COUNT) -> list[dict]:
        """Search XHS notes for multiple keywords and return combined results."""
        loop = asyncio.get_event_loop()
        results: list[dict] = []
        for kw in keywords:
            notes = await loop.run_in_executor(
                None, lambda k=kw: search_xhs(k, count=max_notes_per_keyword)
            )
            results.extend(notes)
        return results
