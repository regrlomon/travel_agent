import pytest
from unittest.mock import AsyncMock, patch
from tools.tavily import search_travel_articles


@pytest.mark.asyncio
async def test_search_returns_content_list(mocker):
    mock_client = mocker.patch("tools.tavily.AsyncTavilyClient")
    instance = AsyncMock()
    instance.search.return_value = {
        "results": [
            {"title": "川西攻略", "content": "稻城亚丁很美...", "url": "http://mafengwo.cn/1"},
            {"title": "四姑娘山", "content": "双桥沟徒步...", "url": "http://qyer.com/2"},
        ]
    }
    mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

    results = await search_travel_articles(["川西 攻略"], api_key="fake")
    assert len(results) == 2
    assert results[0]["content"] == "稻城亚丁很美..."


@pytest.mark.asyncio
async def test_search_multiple_keywords(mocker):
    mock_client = mocker.patch("tools.tavily.AsyncTavilyClient")
    instance = AsyncMock()
    instance.search.return_value = {"results": [{"title": "t", "content": "c", "url": "u"}]}
    mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

    results = await search_travel_articles(["川西 攻略", "稻城 游记"], api_key="fake")
    assert len(results) == 2   # one result per keyword call
    assert instance.search.call_count == 2
