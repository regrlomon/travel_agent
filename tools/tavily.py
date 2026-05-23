from tavily import AsyncTavilyClient
from langsmith import traceable


async def search_travel_articles(keywords: list[str], api_key: str) -> list[dict]:
    """Search travel articles on Mafengwo/Qyer for each keyword. Returns list of {title, content, url}."""
    results: list[dict] = []
    async with AsyncTavilyClient(api_key=api_key) as client:
        for kw in keywords:
            resp = await client.search(
                query=kw,
                search_depth="advanced",
                max_results=5,
                include_domains=["mafengwo.cn", "qyer.com", "lvyou.baidu.com"],
            )
            results.extend(resp.get("results", []))
    return results


class TavilyClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    @traceable(name="tavily_search")
    async def search_travel_articles(self, keywords: list[str]) -> list[dict]:
        return await search_travel_articles(keywords, api_key=self.api_key)
