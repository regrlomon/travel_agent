import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tools.xhs_scraper import scrape_xhs_notes


@pytest.mark.asyncio
async def test_scrape_returns_note_list(mocker):
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[
        MagicMock(inner_text=AsyncMock(return_value="川西超美的稻城亚丁，路很难走但值得")),
        MagicMock(inner_text=AsyncMock(return_value="四姑娘山徒步攻略，感谢XX品牌赞助")),
    ])

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)

    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.xhs_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)

        notes = await scrape_xhs_notes(["川西 攻略"], max_notes_per_keyword=2)

    assert len(notes) == 2
    assert "稻城亚丁" in notes[0]["content"]


@pytest.mark.asyncio
async def test_scrape_respects_delay(mocker):
    mock_sleep = mocker.patch("asyncio.sleep", new_callable=AsyncMock)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.xhs_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)
        await scrape_xhs_notes(["川西 攻略"])

    mock_sleep.assert_called()
